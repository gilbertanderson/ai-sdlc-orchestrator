import json

from langgraph.types import Command

from sdlc_orchestrator.graph import build_graph


def _run(graph, graph_input, thread):
    cfg = {"configurable": {"thread_id": thread}}
    events, interrupt, report = [], None, None
    for mode, chunk in graph.stream(graph_input, cfg, stream_mode=["custom", "updates"]):
        if mode == "custom":
            events.append(chunk)
        elif "__interrupt__" in chunk:
            interrupt = chunk["__interrupt__"][0].value
        elif "finalize" in chunk:
            report = chunk["finalize"]["report"]
    return events, interrupt, report


def test_full_run_pauses_for_review_then_writes_artifacts(demo_repo, tmp_path):
    g = build_graph()
    events, payload, report = _run(g, {"run_id": "r1", "repo": str(demo_repo), "base": "main", "head": "feature/discounts"}, "r1")

    assert report is None and payload is not None, "graph must stop at human review"
    agents = {e["agent"] for e in events}
    assert {"planner", "summarizer", "tests", "security"} <= agents

    rules = {f["rule"] for f in payload["findings"]}
    assert {"SEC003", "SEC004", "SEC007", "SEC009"} <= rules

    tests = {t["file"]: t for t in payload["tests"]}
    pricing = tests["invoices/pricing.py"]
    # bulk_tier(50) returns 5, not the documented 10: the loop retries and documents the bug
    assert pricing["attempts"] == 2 and pricing["status"] == "passing"
    assert pricing["suspected_bugs"] == ["test_bulk_tier_example_3"]
    assert "xfail" in pricing["code"]

    secret = next(f for f in payload["findings"] if f["rule"] == "SEC003")
    _, _, report = _run(g, Command(resume={"decision": "approve", "dismissed": [secret["id"]], "note": "ok"}), "r1")
    assert report["status"] == "approved"
    out = tmp_path / "runs" / "r1"
    md = (out / "PR_DESCRIPTION.md").read_text()
    assert "Risk: high" in md and "Suspected bug" in md and "Hardcoded password" not in md
    assert (out / "tests/generated/test_invoices_pricing.py").exists()
    saved = json.loads((out / "security-report.json").read_text())
    assert next(f for f in saved if f["id"] == secret["id"])["dismissed"] is True


def test_reject_writes_no_pr_description(demo_repo, tmp_path):
    g = build_graph()
    _run(g, {"run_id": "r2", "repo": str(demo_repo), "base": "main", "head": "feature/discounts"}, "r2")
    _, _, report = _run(g, Command(resume={"decision": "reject", "note": "not ready"}), "r2")
    assert report["status"] == "rejected"
    assert not (tmp_path / "runs" / "r2" / "PR_DESCRIPTION.md").exists()


def test_apply_tests_writes_into_repo(demo_repo):
    g = build_graph()
    _run(g, {"run_id": "r3", "repo": str(demo_repo), "base": "main", "head": "feature/discounts"}, "r3")
    _, _, report = _run(g, Command(resume={"decision": "approve", "apply_tests": True}), "r3")
    assert report["applied_to_repo"]
    assert (demo_repo / "tests/generated/test_invoices_pricing.py").exists()


def test_diff_only_run_skips_tests():
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n x = 1\n+y = eval(input())\n"
    g = build_graph()
    events, payload, _ = _run(g, {"run_id": "r4", "repo": "", "base": "", "head": "", "diff": diff}, "r4")
    assert payload["tests"] == []
    assert [f["rule"] for f in payload["findings"]] == ["SEC006"]
