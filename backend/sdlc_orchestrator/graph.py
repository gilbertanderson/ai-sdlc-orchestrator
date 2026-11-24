"""The LangGraph workflow.

    observe_diff -> plan --+--> summarize -----------------------------+
                           +--> tests_plan -> tests_write -> tests_run -+--> human_review -> finalize
                           |                      ^            |       |      (interrupt)
                           |                      +-- retry ---+       |
                           +--> security_rules -> security_review -----+

The planner observes the diff and decides which agents run. Each agent follows a
plan-observe-execute loop and streams its reasoning as custom events. The test
agent loops: it writes tests, runs them against a clean checkout, reads the
failures and tries again. `human_review` waits for every branch (defer=True) and
then pauses the graph with `interrupt` until a person approves or rejects.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import operator
from typing import Annotated, Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from . import prompts
from .config import Settings, get_settings
from .diff import FileChange, git_diff, git_log, parse_diff, read_at
from .llm import LLM, get_llm
from .report import render_pr_description
from .security_rules import RULES, SEVERITY_ORDER, Finding, scan
from .testrunner import Checkout, changed_functions, module_path, run_pytest, symbols

MAX_PROMPT_DIFF = 60_000


class RunState(TypedDict, total=False):
    run_id: str
    repo: str
    base: str
    head: str
    diff: str
    commits: list[str]
    files: list[dict]
    plan: dict
    summary: dict
    test_jobs: list[dict]
    test_round: int
    findings: list[dict]
    security: dict
    review: dict
    report: dict
    errors: Annotated[list[str], operator.add]


def emit(agent: str, phase: str, message: str, **data: Any) -> None:
    """Stream one event to whoever is watching (the dashboard or the CLI)."""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"type": "event", "agent": agent, "phase": phase, "message": message, "data": data, "ts": time.time()})


def _diff_for_prompt(diff: str) -> str:
    return diff if len(diff) <= MAX_PROMPT_DIFF else diff[:MAX_PROMPT_DIFF] + "\n... [diff truncated]"


def build_graph(llm: LLM | None = None, settings: Settings | None = None, checkpointer=None):
    settings = settings or get_settings()
    llm = llm or get_llm(settings)

    # ------------------------------------------------------------------ observe
    def observe_diff(state: RunState) -> dict:
        emit("planner", "observe", "Reading the diff")
        diff = state.get("diff") or ""
        commits: list[str] = []
        if not diff and state.get("repo"):
            diff = git_diff(state["repo"], state["base"], state.get("head", "HEAD"))
        if state.get("repo") and state.get("base"):
            try:
                commits = git_log(state["repo"], state["base"], state.get("head", "HEAD"))
            except Exception:
                commits = []
        changes = parse_diff(diff)
        files = []
        for c in changes:
            d = c.to_dict()
            d.pop("patch")
            d["added_lines"] = [{"line": a.line, "text": a.text} for a in c.added_lines]
            src = read_at(state["repo"], state.get("head", "HEAD"), c.path) if state.get("repo") and c.status != "deleted" else None
            d["symbols"] = symbols(src) if src and c.language == "python" else []
            files.append(d)
        adds = sum(f["additions"] for f in files)
        dels = sum(f["deletions"] for f in files)
        emit("planner", "observe", f"{len(files)} files changed, +{adds}/-{dels}, {len(commits)} commits",
             files=[{k: f[k] for k in ("path", "status", "language", "additions", "deletions")} for f in files])
        return {"diff": diff, "commits": commits, "files": files}

    # --------------------------------------------------------------------- plan
    def plan(state: RunState) -> dict:
        files = state["files"]
        if not files:
            emit("planner", "plan", "The diff is empty; nothing to do")
            return {"plan": {"agents": [], "focus": [], "reasoning": "The diff is empty."}}
        ctx = {
            "files": [{k: v for k, v in f.items() if k != "added_lines"} for f in files],
            "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files),
            "commits": state.get("commits", []),
        }
        emit("planner", "plan", f"Choosing agents with {llm.name}")
        result = llm.run("plan", prompts.PLANNER, "Diff overview:\n" + json.dumps(ctx, indent=1), ctx)
        agents = [a for a in result.get("agents", []) if a in {"summarize", "tests", "security"}]
        if "summarize" not in agents:
            agents.insert(0, "summarize")
        result["agents"] = agents
        emit("planner", "plan", result.get("reasoning", ""), agents=agents, focus=result.get("focus", []))
        return {"plan": result}

    def route_agents(state: RunState) -> list[str]:
        agents = state["plan"]["agents"]
        nodes = []
        if "summarize" in agents:
            nodes.append("summarize")
        if "tests" in agents:
            nodes.append("tests_plan")
        if "security" in agents:
            nodes.append("security_rules")
        return nodes or ["human_review"]

    # ---------------------------------------------------------------- summarize
    def summarize(state: RunState) -> dict:
        files = state["files"]
        emit("summarizer", "observe", f"Reading {len(files)} changed files and {len(state.get('commits', []))} commit messages")
        ctx = {
            "files": [{k: v for k, v in f.items() if k != "added_lines"} for f in files],
            "additions": sum(f["additions"] for f in files),
            "deletions": sum(f["deletions"] for f in files),
            "commits": state.get("commits", []),
        }
        user = "Commits:\n" + "\n".join(ctx["commits"] or ["(none)"]) + "\n\nDiff:\n" + _diff_for_prompt(state["diff"])
        emit("summarizer", "execute", "Drafting the PR title, description and risk assessment")
        result = llm.run("summarize", prompts.SUMMARIZER, user, ctx)
        emit("summarizer", "done", result.get("reasoning", ""), title=result.get("title"), risk=result.get("risk"))
        return {"summary": result}

    # -------------------------------------------------------------------- tests
    def tests_plan(state: RunState) -> dict:
        jobs = []
        candidates = [
            f for f in state["files"]
            if f["language"] == "python" and not f["is_test"] and f["status"] != "deleted" and f["additions"] > 0
        ]
        for f in candidates[: settings.max_test_files]:
            src = read_at(state["repo"], state.get("head", "HEAD"), f["path"]) if state.get("repo") else None
            if not src:
                continue
            change = FileChange(path=f["path"])
            change.added_lines = [_Added(a["line"], a["text"]) for a in f["added_lines"]]
            funcs = changed_functions(src, change)
            if not funcs:
                continue
            mod = module_path(f["path"])
            jobs.append({
                "file": f["path"],
                "module": mod,
                "functions": funcs,
                "test_path": f"tests/generated/test_{mod.replace('.', '_')}.py",
                "attempts": 0,
                "status": "pending",
                "code": "",
                "output": "",
                "history": [],
            })
        skipped = len(candidates) - len(jobs)
        msg = f"Planned tests for {len(jobs)} file(s): " + ", ".join(f"{j['file']} ({', '.join(j['functions'])})" for j in jobs)
        if skipped > 0:
            msg += f". Skipped {skipped} file(s) with no changed top-level functions or over the limit."
        emit("tests", "plan", msg if jobs else "No changed top-level Python functions to test", jobs=[j["file"] for j in jobs])
        return {"test_jobs": jobs, "test_round": 0}

    def tests_write(state: RunState) -> dict:
        jobs = [dict(j) for j in state["test_jobs"]]
        for j in jobs:
            if j["status"] not in {"pending", "failing"}:
                continue
            src = read_at(state["repo"], state.get("head", "HEAD"), j["file"]) or ""
            retry = j["status"] == "failing"
            ctx = {
                "module": j["module"],
                "source": src,
                "functions": j["functions"],
                "previous_code": j["code"] if retry else None,
                "previous_output": j["output"] if retry else None,
            }
            user = (
                f"Module path: {j['module']}\nFile: {j['file']}\nChanged functions: {', '.join(j['functions'])}\n\n"
                f"Source:\n```python\n{src}\n```"
            )
            if retry:
                user += f"\n\nYour previous test file:\n```python\n{j['code']}\n```\n\npytest output:\n```\n{j['output'][-4000:]}\n```"
            emit("tests", "execute", ("Rewriting" if retry else "Writing") + f" tests for {j['file']} (attempt {j['attempts'] + 1})")
            result = llm.run("write_tests", prompts.TEST_WRITER, user, ctx)
            j["code"] = result.get("test_code", "")
            j["attempts"] += 1
            j["suspected_bugs"] = result.get("suspected_bugs", [])
            j["reasoning"] = result.get("reasoning", "")
            j["status"] = "written"
            emit("tests", "execute", j["reasoning"], file=j["file"], attempt=j["attempts"], code=j["code"])
        return {"test_jobs": jobs, "test_round": state.get("test_round", 0) + 1}

    def tests_run(state: RunState) -> dict:
        jobs = [dict(j) for j in state["test_jobs"]]
        pending = [j for j in jobs if j["status"] == "written"]
        if not pending:
            return {"test_jobs": jobs}
        checkout = Checkout(state["repo"], state.get("head", "HEAD"))
        try:
            for j in pending:
                emit("tests", "observe", f"Running pytest on {j['test_path']} against a clean checkout of {state.get('head', 'HEAD')}")
                run = run_pytest(checkout, j["test_path"], j["code"], settings.test_timeout_s)
                j["output"] = run.output
                j["counts"] = run.counts
                j["history"] = j["history"] + [{"attempt": j["attempts"], "passed": run.passed, "counts": run.counts}]
                if run.passed:
                    j["status"] = "passing"
                elif j["attempts"] >= settings.max_test_attempts:
                    j["status"] = "gave_up"
                else:
                    j["status"] = "failing"
                counts = ", ".join(f"{v} {k}" for k, v in run.counts.items()) or f"exit code {run.exit_code}"
                emit("tests", "observe", f"{j['file']}: {counts}", file=j["file"], status=j["status"], output=run.output[-2500:])
        finally:
            checkout.cleanup()
        return {"test_jobs": jobs}

    def tests_next(state: RunState) -> Literal["tests_write", "human_review"]:
        if any(j["status"] == "failing" for j in state["test_jobs"]):
            emit("tests", "plan", "Some tests failed; feeding the failures back for another attempt")
            return "tests_write"
        done = state["test_jobs"]
        emit("tests", "done", f"{sum(j['status'] == 'passing' for j in done)} of {len(done)} test file(s) passing",
             jobs=[{"file": j["file"], "status": j["status"], "attempts": j["attempts"]} for j in done])
        return "human_review"

    # ----------------------------------------------------------------- security
    def security_rules(state: RunState) -> dict:
        changes = []
        for f in state["files"]:
            c = FileChange(path=f["path"], status=f["status"], language=f["language"])
            c.added_lines = [_Added(a["line"], a["text"]) for a in f["added_lines"]]
            changes.append(c)
        n_lines = sum(len(c.added_lines) for c in changes)
        emit("security", "observe", f"Running {len(RULES)} deterministic rules over {n_lines} added lines")
        hits = [h.to_dict() for h in scan(changes)]
        emit("security", "observe", f"{len(hits)} candidate finding(s) from rules",
             candidates=[{k: h[k] for k in ("id", "title", "severity", "file", "line")} for h in hits])
        return {"findings": hits}

    def security_review(state: RunState) -> dict:
        candidates = state.get("findings", [])
        emit("security", "execute", f"Reviewing {len(candidates)} candidate(s) in context and looking for issues the rules miss")
        ctx = {"candidates": candidates}
        user = (
            "Candidate findings:\n" + json.dumps(candidates, indent=1)
            + "\n\nPatch (added lines are prefixed with +):\n" + _diff_for_prompt(state["diff"])
        )
        result = llm.run("security_review", prompts.SECURITY, user, ctx)
        by_id = {c["id"]: dict(c) for c in candidates}
        final: list[dict] = []
        for conf in result.get("confirmed", []):
            if conf.get("id") in by_id:
                f = by_id.pop(conf["id"])
                f["severity"] = conf.get("severity", f["severity"])
                f["explanation"] = conf.get("explanation", "")
                final.append(f)
        fps = []
        for fp in result.get("false_positives", []):
            if fp.get("id") in by_id:
                f = by_id.pop(fp["id"])
                fps.append({**f, "explanation": fp.get("explanation", ""), "dismissed": True})
        final.extend(by_id.values())  # anything the model ignored stays in, unreviewed
        for i, add in enumerate(result.get("additional", []), 1):
            final.append(Finding(
                id=f"LLM{i:03d}-{add.get('file', '?')}:{add.get('line', 0)}", rule="LLM", title=add.get("title", "Issue"),
                severity=add.get("severity", "medium"), cwe=add.get("cwe", ""), file=add.get("file", ""),
                line=int(add.get("line", 0) or 0), snippet="", fix=add.get("fix", ""), source="llm",
                explanation=add.get("explanation", ""),
            ).to_dict())
        final.sort(key=lambda x: (SEVERITY_ORDER.get(x["severity"], 9), x["file"], x["line"]))
        counts = {s: sum(f["severity"] == s for f in final) for s in SEVERITY_ORDER}
        emit("security", "done", result.get("reasoning", ""), counts=counts, dismissed=len(fps))
        return {"findings": final + fps, "security": {"reasoning": result.get("reasoning", ""), "counts": counts}}

    # ------------------------------------------------------------ human review
    def human_review(state: RunState) -> dict:
        # The node re-runs from the top on resume, so the "waiting" event is sent by
        # the caller when it sees the interrupt, not here.
        decision = interrupt({
            "summary": with_security_risk(state.get("summary") or {}, state.get("findings", []), set()),
            "findings": state.get("findings", []),
            "tests": [
                {k: j.get(k) for k in ("file", "test_path", "status", "attempts", "code", "counts", "suspected_bugs", "reasoning")}
                for j in state.get("test_jobs", [])
            ],
        })
        decision = decision if isinstance(decision, dict) else {"decision": str(decision)}
        verdict = decision.get("decision", "approve")
        emit("orchestrator", "review", f"Reviewer chose: {verdict}" + (f" ({decision['note']})" if decision.get("note") else ""))
        return {"review": decision}

    # ----------------------------------------------------------------- finalize
    def finalize(state: RunState) -> dict:
        review = state.get("review", {})
        approved = review.get("decision", "approve") == "approve"
        summary = dict(state.get("summary") or {})
        summary = with_security_risk(summary, state.get("findings", []), set(review.get("dismissed", [])))
        if review.get("title"):
            summary["title"] = review["title"]
        dismissed = set(review.get("dismissed", []))
        findings = [{**f, "dismissed": f.get("dismissed") or f["id"] in dismissed} for f in state.get("findings", [])]
        include_tests = approved and review.get("include_tests", True)
        tests = [j for j in state.get("test_jobs", []) if j["status"] == "passing"] if include_tests else []

        out = settings.runs_dir / state["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        files_written = []
        if approved:
            md = render_pr_description(summary, findings, state.get("test_jobs", []), review.get("note", ""))
            (out / "PR_DESCRIPTION.md").write_text(md)
            files_written.append("PR_DESCRIPTION.md")
            for j in tests:
                p = out / j["test_path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(j["code"])
                files_written.append(j["test_path"])
                if review.get("apply_tests") and state.get("repo"):
                    target = Path(state["repo"]) / j["test_path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(j["code"])
        (out / "security-report.json").write_text(json.dumps(findings, indent=2))
        files_written.append("security-report.json")
        report = {
            "status": "approved" if approved else "rejected",
            "output_dir": str(out),
            "files": files_written,
            "applied_to_repo": bool(review.get("apply_tests")) and approved,
            "summary": summary,
            "open_findings": sum(not f["dismissed"] for f in findings),
            "tests_passing": sum(j["status"] == "passing" for j in state.get("test_jobs", [])),
        }
        (out / "run.json").write_text(json.dumps({**report, "plan": state.get("plan"), "review": review}, indent=2))
        emit("orchestrator", "done", f"Run {report['status']}. Wrote {len(files_written)} file(s) to {out}", report=report)
        return {"report": report}

    g = StateGraph(RunState)
    g.add_node("observe_diff", observe_diff)
    g.add_node("plan", plan)
    g.add_node("summarize", summarize)
    g.add_node("tests_plan", tests_plan)
    g.add_node("tests_write", tests_write)
    g.add_node("tests_run", tests_run)
    g.add_node("security_rules", security_rules)
    g.add_node("security_review", security_review)
    g.add_node("human_review", human_review, defer=True)
    g.add_node("finalize", finalize)

    g.add_edge(START, "observe_diff")
    g.add_edge("observe_diff", "plan")
    g.add_conditional_edges("plan", route_agents, ["summarize", "tests_plan", "security_rules", "human_review"])
    g.add_edge("summarize", "human_review")
    g.add_conditional_edges("tests_plan", lambda s: "tests_write" if s["test_jobs"] else "human_review",
                            ["tests_write", "human_review"])
    g.add_edge("tests_write", "tests_run")
    g.add_conditional_edges("tests_run", tests_next, ["tests_write", "human_review"])
    g.add_edge("security_rules", "security_review")
    g.add_edge("security_review", "human_review")
    g.add_edge("human_review", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


def with_security_risk(summary: dict, findings: list[dict], dismissed: set[str]) -> dict:
    """Raise the PR risk to high while critical or high findings are still open."""
    serious = [f for f in findings if not f.get("dismissed") and f["id"] not in dismissed and f["severity"] in {"critical", "high"}]
    if not serious or not summary:
        return summary
    return {
        **summary,
        "risk": "high",
        "risk_reasons": [*summary.get("risk_reasons", []), f"{len(serious)} open critical or high security finding(s)"],
    }


class _Added:
    __slots__ = ("line", "text")

    def __init__(self, line: int, text: str):
        self.line, self.text = line, text
