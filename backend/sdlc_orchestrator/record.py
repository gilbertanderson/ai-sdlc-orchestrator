"""Recording real runs for the browser demo.

`sdlc-orchestrator record` runs a demo scenario through the real graph, stops at
the human review, and saves what the dashboard needs to replay the run with no
server: every message the server would have sent over the WebSocket with its time
offset, the diff under review, and the summary as the agent wrote it before the
security risk rule was applied.

It also saves golden outputs for a few review decisions. The frontend tests use
them to check that the browser's port of `prepare_outputs` matches Python exactly.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .demo import SCENARIOS, get_scenario, make_demo_repo
from .graph import build_graph, prepare_outputs
from .llm import LLM, get_llm

FORMAT = 1
WAITING = "Waiting for a human to approve, edit or reject"


def model_label(name: str) -> str:
    """A readable name for the model behind a run, e.g. 'Claude Sonnet 4.5 on Amazon Bedrock'."""
    if name == "offline-heuristics":
        return "Offline heuristic model"
    if not name.startswith("bedrock:"):
        return name
    model_id = name.split(":", 1)[1]
    new = re.search(r"claude-(opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?=-\d{8}|-v\d|:|$)", model_id)
    old = re.search(r"claude-(\d+)(?:-(\d{1,2}))?-(opus|sonnet|haiku)", model_id)
    if new:
        family, major, minor = new.group(1), new.group(2), new.group(3)
    elif old:
        major, minor, family = old.group(1), old.group(2), old.group(3)
    else:
        return f"{model_id} on Amazon Bedrock"
    version = f"{major}.{minor}" if minor else major
    return f"Claude {family.capitalize()} {version} on Amazon Bedrock"


def _scrubber() -> Any:
    """Remove machine-specific paths and AWS resource names from recorded text."""
    temp_dirs = {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())}
    homes = {str(Path.home()), os.path.realpath(Path.home())}
    rules = [(re.compile(re.escape(t) + r"[\\/]+sdlc-[a-z]+-[\w.-]+(?:[\\/]+(?:repo[\\/]+)?)?"), "") for t in temp_dirs]
    rules += [(re.compile(re.escape(h) + r"(?=[\\/])"), "~") for h in homes if len(h) > 1]
    rules.append((re.compile(r"arn:aws[\w-]*:[^\s\"']+"), "arn:aws:(removed)"))

    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            for pattern, repl in rules:
                value = pattern.sub(repl, value)
            return value
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value

    return scrub


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)


def public_warnings(recording: dict) -> list[str]:
    """Things a person should look at before publishing a recording."""
    text = "\n".join(_strings(recording))
    warnings = []
    if re.search(r"(?<!\d)\d{12}(?!\d)", text):
        warnings.append("contains a 12-digit number that could be an AWS account ID")
    if "arn:aws:" in text.replace("arn:aws:(removed)", ""):
        warnings.append("still contains an AWS ARN")
    for marker in sorted({tempfile.gettempdir(), str(Path.home())}):
        if len(marker) > 1 and marker in text:
            warnings.append(f"still mentions {marker}")
    return warnings


def golden_cases(payload: dict) -> list[dict]:
    """Review decisions whose outputs the browser must reproduce."""
    open_ids = [f["id"] for f in payload.get("findings", []) if not f.get("dismissed")]

    def review(**kw: Any) -> dict:
        return {"decision": "approve", "title": None, "note": "", "dismissed": [], "include_tests": True, "apply_tests": False, **kw}

    return [
        {"name": "approve as is", "review": review()},
        {
            "name": "approve with edits",
            "review": review(title="Reviewed by a human ✓", note="Rotate the key before merging. Looks good otherwise ✓",
                             dismissed=open_ids[:1], include_tests=False),
        },
        {"name": "dismiss every finding", "review": review(dismissed=open_ids)},
        {"name": "reject", "review": review(decision="reject", note="Not ready yet.")},
    ]


def record(scenario: str, llm: LLM | None = None, settings: Settings | None = None) -> tuple[dict, dict]:
    """Run one scenario up to the human review. Returns (recording, golden)."""
    settings = settings or get_settings()
    llm = llm or get_llm(settings)
    spec = get_scenario(scenario)
    provider = llm.name.split(":", 1)[0]
    rec_id = spec.id if provider == "offline-heuristics" else f"{spec.id}-{provider}"

    with tempfile.TemporaryDirectory(prefix="sdlc-record-") as tmp:
        repo = make_demo_repo(Path(tmp) / "repo", spec.id)
        graph = build_graph(llm, settings)
        cfg = {"configurable": {"thread_id": rec_id}}
        graph_input = {"run_id": rec_id, "repo": str(repo), "base": spec.base, "head": spec.head}
        started = time.time()
        events: list[dict] = []
        payload = None
        for mode, chunk in graph.stream(graph_input, cfg, stream_mode=["custom", "updates"]):
            if mode == "custom":
                events.append(chunk)
            elif "__interrupt__" in chunk:
                payload = chunk["__interrupt__"][0].value
        finished = time.time()
        if payload is None:
            raise RuntimeError(f"scenario {scenario!r} finished without pausing for review")
        state = graph.get_state(cfg).values

    messages = [{"t": round(max(e["ts"] - started, 0), 3), "m": {k: v for k, v in e.items() if k != "ts"}} for e in events]
    t_end = round(finished - started, 3)
    messages.append({"t": t_end, "m": {"type": "event", "agent": "orchestrator", "phase": "review", "message": WAITING, "data": {}}})
    messages.append({"t": t_end, "m": {"type": "status", "status": "awaiting_review", "review": payload, "report": None, "error": None}})

    scrub = _scrubber()
    order = list(SCENARIOS).index(spec.id) * 2 + (1 if provider == "offline-heuristics" else 0)
    recording = scrub({
        "format": FORMAT,
        "id": rec_id,
        "scenario": spec.id,
        "title": spec.title,
        "blurb": spec.blurb,
        "order": order,
        "model": llm.name,
        "model_label": model_label(llm.name),
        "recorded_at": dt.date.today().isoformat(),
        "duration_s": t_end,
        "request": {"repo": None, "base": spec.base, "head": spec.head, "demo": True, "scenario": spec.id},
        "commits": state.get("commits", []),
        "diff": state.get("diff", ""),
        "base_summary": state.get("summary") or {},
        "messages": messages,
    })

    review_payload = recording["messages"][-1]["m"]["review"]
    cases = []
    for case in golden_cases(review_payload):
        out = prepare_outputs(recording["base_summary"], review_payload["findings"], review_payload["tests"], case["review"])
        out.pop("tests")
        cases.append({**case, "expected": out})
    golden = {"format": FORMAT, "id": rec_id, "cases": cases}
    return recording, golden


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def write_recording(recording: dict, golden: dict, out_dir: Path, golden_dir: Path | None = None) -> Path:
    """Save a recording, refresh the scenario index next to it, and save its golden file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{recording['id']}.json"
    path.write_text(_dump(recording), encoding="utf-8")

    index_path = out_dir / "index.json"
    runs = json.loads(index_path.read_text(encoding="utf-8"))["runs"] if index_path.exists() else []
    entry = {k: recording[k] for k in ("id", "scenario", "title", "blurb", "order", "model", "model_label", "recorded_at", "duration_s")}
    entry["file"] = path.name
    runs = [r for r in runs if r["id"] != recording["id"] and (out_dir / r["file"]).exists()] + [entry]
    runs.sort(key=lambda r: (r["order"], r["id"]))
    index_path.write_text(_dump({"format": FORMAT, "runs": runs}), encoding="utf-8")

    if golden_dir is not None:
        golden_dir.mkdir(parents=True, exist_ok=True)
        (golden_dir / f"{recording['id']}.json").write_text(_dump(golden), encoding="utf-8")
    return path
