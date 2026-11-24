"""Model access.

Every agent calls `LLM.run(task, system, user, context)` and gets back a dict.
`BedrockLLM` sends the system and user prompts to AWS Bedrock and parses the JSON
reply. `OfflineLLM` answers the same tasks with deterministic heuristics over the
structured `context`, so the pipeline, the tests and the demo run without credentials.
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from pathlib import PurePosixPath
from typing import Any, Protocol

from .config import Settings


class LLM(Protocol):
    name: str

    def run(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]: ...


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply, tolerating fences and stray prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("model reply contained no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("model reply contained an unterminated JSON object")


class BedrockLLM:
    def __init__(self, settings: Settings):
        from langchain_aws import ChatBedrockConverse

        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._model = ChatBedrockConverse(
            model=settings.bedrock_model_id,
            region_name=settings.aws_region,
            temperature=0,
            max_tokens=4096,
        )

    def run(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]:
        messages = [("system", system), ("human", user)]
        reply = self._model.invoke(messages)
        try:
            return extract_json(_text(reply.content))
        except (ValueError, json.JSONDecodeError):
            messages += [("ai", _text(reply.content)), ("human", "That was not valid JSON. Reply with only the JSON object.")]
            return extract_json(_text(self._model.invoke(messages).content))


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if isinstance(part, dict))


# --------------------------------------------------------------------------- offline


SENSITIVE_PATHS = re.compile(r"(?i)(auth|login|security|crypto|payment|billing|migration|infra|terraform|deploy|\.github/workflows|docker)")


class OfflineLLM:
    """Deterministic stand-in for a model. Good enough to exercise every graph path."""

    name = "offline-heuristics"

    def run(self, task: str, system: str, user: str, context: dict[str, Any]) -> dict[str, Any]:
        return getattr(self, f"_{task}")(context)

    # planner -----------------------------------------------------------------
    def _plan(self, ctx: dict[str, Any]) -> dict[str, Any]:
        files = ctx["files"]
        py_src = [f for f in files if f["language"] == "python" and not f["is_test"] and f["status"] != "deleted"]
        code = [f for f in files if f["is_code"] or f["language"] in {"yaml", "json"}]
        agents, focus = ["summarize"], [f"summarize: {len(files)} files, +{ctx['additions']}/-{ctx['deletions']}"]
        if py_src:
            agents.append("tests")
            focus.append("tests: " + ", ".join(f["path"] for f in py_src[:3]))
        if code:
            agents.append("security")
            focus.append(f"security: {sum(f['additions'] for f in code)} added lines across {len(code)} files")
        skipped = []
        if "tests" not in agents:
            skipped.append("tests (no Python source changes)")
        if "security" not in agents:
            skipped.append("security (no code or config changes)")
        reasoning = f"The diff touches {len(files)} files. Running {', '.join(agents)}."
        if skipped:
            reasoning += " Skipping " + "; ".join(skipped) + "."
        return {"agents": agents, "focus": focus, "reasoning": reasoning}

    # summarizer --------------------------------------------------------------
    def _summarize(self, ctx: dict[str, Any]) -> dict[str, Any]:
        files, commits = ctx["files"], ctx.get("commits", [])
        title = commits[0] if len(commits) == 1 else (
            f"{commits[-1]} (+{len(commits) - 1} more)" if commits else f"Update {len(files)} files"
        )
        changes = []
        for f in files:
            verb = {"added": "Add", "deleted": "Remove", "renamed": "Rename"}.get(f["status"], "Update")
            symbols = ", ".join(f.get("symbols", [])[:4])
            changes.append(f"{verb} `{f['path']}`" + (f" ({symbols})" if symbols else "") + f", +{f['additions']}/-{f['deletions']}")
        total = ctx["additions"] + ctx["deletions"]
        sensitive = [f["path"] for f in files if SENSITIVE_PATHS.search(f["path"])]
        untested = [f["path"] for f in files if f["is_code"] and not f["is_test"]] and not any(f["is_test"] for f in files)
        risk_reasons = []
        if total > 400:
            risk_reasons.append(f"Large change ({total} lines)")
        if sensitive:
            risk_reasons.append("Touches sensitive areas: " + ", ".join(sensitive[:3]))
        if untested:
            risk_reasons.append("Code changed with no test changes in the diff")
        risk = "high" if len(risk_reasons) >= 2 or total > 800 else "medium" if risk_reasons else "low"
        langs = sorted({f["language"] for f in files if f["language"] != "other"})
        summary = (
            f"This PR changes {len(files)} file{'s' if len(files) != 1 else ''}"
            + (f" ({', '.join(langs)})" if langs else "")
            + f" with {ctx['additions']} additions and {ctx['deletions']} deletions."
        )
        if commits:
            summary += " Commits: " + "; ".join(commits[:5]) + "."
        checklist = ["Behavior matches the PR title and description"]
        if any(f["language"] == "python" for f in files):
            checklist.append("New Python functions handle invalid input and empty values")
        if sensitive:
            checklist.append("Changes in sensitive paths have a second reviewer")
        if untested:
            checklist.append("Generated tests are reviewed and committed, or tests are added by hand")
        return {
            "title": title[:72],
            "summary": summary,
            "changes": changes,
            "risk": risk,
            "risk_reasons": risk_reasons or ["Small, contained change"],
            "testing_notes": ["Run the unit test suite", "Exercise the changed code paths locally"],
            "reviewer_checklist": checklist,
            "reasoning": f"Risk is {risk} because: " + ("; ".join(risk_reasons) if risk_reasons else "the change is small and contained") + ".",
        }

    # test writer -------------------------------------------------------------
    def _write_tests(self, ctx: dict[str, Any]) -> dict[str, Any]:
        failing = set(re.findall(r"FAILED \S+::(test_\w+)", ctx.get("previous_output") or ""))
        if ctx.get("previous_code") and failing:
            code = _mark_xfail(ctx["previous_code"], failing)
            return {
                "test_code": code,
                "covers": ctx["functions"],
                "suspected_bugs": sorted(failing),
                "reasoning": (
                    f"{len(failing)} test(s) failed against the documented examples. The expectations come from the "
                    "function's own docstring, so the code is more likely wrong than the test. Marked them xfail so the "
                    "suite passes while the suspected bug stays visible."
                ),
            }
        code, covers, notes = _tests_from_source(ctx["module"], ctx["source"], ctx["functions"])
        return {
            "test_code": code,
            "covers": covers,
            "suspected_bugs": [],
            "reasoning": f"Wrote {notes} for {', '.join(covers) or 'the module'}: assertions from docstring examples where present, plus signature and smoke checks.",
        }

    # security ----------------------------------------------------------------
    def _security_review(self, ctx: dict[str, Any]) -> dict[str, Any]:
        confirmed, false_positives = [], []
        for c in ctx["candidates"]:
            snippet = c["snippet"]
            if c["rule"] == "SEC003" and re.search(r"(?i)(example|dummy|placeholder|changeme|xxx|<.*>)", snippet):
                false_positives.append({"id": c["id"], "explanation": "The value looks like a placeholder, not a real secret."})
                continue
            if c["file"].startswith(("tests/", "test/")) and c["severity"] in {"low", "medium"}:
                false_positives.append({"id": c["id"], "explanation": "Only in test code."})
                continue
            confirmed.append({"id": c["id"], "severity": c["severity"], "explanation": f"{c['title']} on an added line in {c['file']}."})
        return {
            "confirmed": confirmed,
            "false_positives": false_positives,
            "additional": [],
            "reasoning": f"Checked {len(ctx['candidates'])} rule hits: {len(confirmed)} confirmed, {len(false_positives)} dismissed as false positives. The offline model does not look for issues beyond the rules.",
        }


def _mark_xfail(code: str, names: set[str]) -> str:
    out = []
    for line in code.splitlines():
        m = re.match(r"^def (test_\w+)\(", line)
        if m and m.group(1) in names:
            out.append('@pytest.mark.xfail(reason="Fails against the docstring example; likely a bug in the code under test", strict=True)')
        out.append(line)
    return "\n".join(out) + "\n"


def _tests_from_source(module: str, source: str, functions: list[str]) -> tuple[str, list[str], str]:
    tree = ast.parse(source)
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    targets = [name for name in functions if name in defs and not name.startswith("_")] or [
        n for n in defs if not n.startswith("_")
    ]
    alias = PurePosixPath(module.replace(".", "/")).name
    lines = ["import inspect", "", "import pytest", "", f"import {module} as {alias}", ""]
    n_examples = n_smoke = 0
    for name in targets:
        fn = defs[name]
        examples = _doc_examples(ast.get_docstring(fn) or "")
        for i, (expr, expected) in enumerate(examples, 1):
            lines += ["", f"def test_{name}_example_{i}():"]
            if expected.startswith("Traceback") or re.match(r"^\w+Error", expected):
                exc = re.search(r"(\w+(?:Error|Exception))", expected.splitlines()[-1])
                lines.append(f"    with pytest.raises({exc.group(1) if exc else 'Exception'}):")
                lines.append(f"        {alias}.{expr}")
            else:
                lines.append(f"    assert {alias}.{expr} == {expected}")
            n_examples += 1
        params = [a.arg for a in fn.args.args]
        lines += [
            "",
            f"def test_{name}_signature():",
            f"    assert callable({alias}.{name})",
            f"    assert list(inspect.signature({alias}.{name}).parameters) == {params!r}",
        ]
        n_smoke += 1
    note = f"{n_examples} example-based test(s) and {n_smoke} signature check(s)"
    return textwrap.dedent("\n".join(lines)).strip() + "\n", targets, note


def _doc_examples(doc: str) -> list[tuple[str, str]]:
    examples, lines, i = [], doc.splitlines(), 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(">>> "):
            expr = line[4:]
            expected = []
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(">>>"):
                expected.append(lines[i].strip())
                i += 1
            if expected:
                examples.append((expr, "\n".join(expected) if expected[0].startswith("Traceback") else expected[0]))
            continue
        i += 1
    return examples


def get_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "bedrock":
        return BedrockLLM(settings)
    if settings.llm_provider == "offline":
        return OfflineLLM()
    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}; use 'bedrock' or 'offline'")
