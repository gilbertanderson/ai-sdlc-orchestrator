import json

import pytest
from langgraph.types import Command

from sdlc_orchestrator.cli import main
from sdlc_orchestrator.demo import get_scenario, make_demo_repo
from sdlc_orchestrator.graph import build_graph, prepare_outputs
from sdlc_orchestrator.record import golden_cases, model_label, public_warnings, record, write_recording


def _final(recording):
    return recording["messages"][-1]["m"]


def _timeline(recording):
    """Each agent's events in order. The agents run in parallel, so their events interleave differently each run."""
    lanes: dict[str, list] = {}
    for m in recording["messages"]:
        if m["m"]["type"] == "event":
            lanes.setdefault(m["m"]["agent"], []).append((m["m"]["phase"], m["m"]["message"]))
    return lanes


@pytest.fixture(scope="module")
def invoicing():
    return record("invoicing")


def test_recording_ends_at_review_with_everything_the_browser_needs(invoicing):
    recording, golden = invoicing
    final = _final(recording)
    assert final == {**final, "type": "status", "status": "awaiting_review"}
    assert recording["request"] == {"repo": None, "base": "main", "head": "feature/discounts", "demo": True, "scenario": "invoicing"}
    assert recording["model_label"] == "Offline heuristic model"
    assert recording["diff"].startswith("diff --git") and recording["commits"]
    times = [m["t"] for m in recording["messages"]]
    assert times == sorted(times) and times[-1] == recording["duration_s"]
    assert all("ts" not in m["m"] for m in recording["messages"])

    review = final["review"]
    assert {f["rule"] for f in review["findings"]} == {"SEC003", "SEC004", "SEC007", "SEC009"}
    assert review["summary"]["risk"] == "high"
    # the base summary is the agent's own, before open findings raised the risk
    assert recording["base_summary"]["risk"] == "medium"
    assert [g["name"] for g in golden["cases"]] == [c["name"] for c in golden_cases(review)]


def test_recordings_hold_no_machine_paths(invoicing):
    recording, golden = invoicing
    assert public_warnings(recording) == []
    assert public_warnings(golden) == []


def test_clean_scenario_passes_first_time():
    recording, _ = record("clean")
    review = _final(recording)["review"]
    assert review["findings"] == []
    assert review["summary"]["risk"] == "low"
    assert [(t["status"], t["attempts"]) for t in review["tests"]] == [("passing", 1)]


def test_offline_recordings_are_deterministic_apart_from_timing():
    a, ga = record("clean")
    b, gb = record("clean")
    assert _timeline(a) == _timeline(b)
    assert ga == gb


def test_golden_outputs_match_a_real_finalize(tmp_path, monkeypatch, invoicing):
    """The golden files are what the browser must reproduce, so they must equal what the real graph writes."""
    recording, golden = invoicing
    spec = get_scenario("invoicing")
    for i, case in enumerate(golden["cases"]):
        repo = make_demo_repo(tmp_path / f"repo{i}", spec.id)
        runs = tmp_path / f"runs{i}"
        monkeypatch.setenv("RUNS_DIR", str(runs))
        g = build_graph()
        cfg = {"configurable": {"thread_id": f"t{i}"}}
        list(g.stream({"run_id": "r", "repo": str(repo), "base": spec.base, "head": spec.head}, cfg))
        state = g.get_state(cfg).values
        # the browser only has the review payload's test fields; they must be enough
        payload_tests = _final(recording)["review"]["tests"]
        full = prepare_outputs(state["summary"], state["findings"], state["test_jobs"], case["review"])
        assert {k: v for k, v in full.items() if k != "tests"} == case["expected"]
        assert prepare_outputs(recording["base_summary"], state["findings"], payload_tests, case["review"])["files"] == full["files"]

        list(g.stream(Command(resume=case["review"]), cfg))
        written = {p.relative_to(runs / "r").as_posix(): p.read_text(encoding="utf-8") for p in (runs / "r").rglob("*") if p.is_file()}
        written.pop("run.json")
        assert written == case["expected"]["files"]


def test_write_recording_keeps_index_in_order(tmp_path, invoicing):
    recording, golden = invoicing
    out, gold = tmp_path / "runs", tmp_path / "golden"
    (out).mkdir()
    (out / "index.json").write_text(json.dumps({"format": 1, "runs": [
        {"id": "gone", "file": "gone.json", "order": 0},
        {"id": "invoicing-bedrock", "file": "invoicing-bedrock.json", "order": 0},
    ]}))
    (out / "invoicing-bedrock.json").write_text("{}")
    write_recording(recording, golden, out, gold)
    index = json.loads((out / "index.json").read_text())
    assert [r["id"] for r in index["runs"]] == ["invoicing-bedrock", "invoicing"]
    assert index["runs"][1]["file"] == "invoicing.json" and index["runs"][1]["title"]
    assert json.loads((gold / "invoicing.json").read_text())["cases"]


def test_record_command(tmp_path, capsys):
    assert main(["record", "--scenario", "clean", "--out-dir", str(tmp_path / "runs")]) == 0
    assert "Recorded clean with Offline heuristic model" in capsys.readouterr().out
    assert (tmp_path / "runs" / "clean.json").exists()


@pytest.mark.parametrize(("name", "label"), [
    ("offline-heuristics", "Offline heuristic model"),
    ("bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0", "Claude Sonnet 4.5 on Amazon Bedrock"),
    ("bedrock:anthropic.claude-opus-4-1-20250805-v1:0", "Claude Opus 4.1 on Amazon Bedrock"),
    ("bedrock:anthropic.claude-sonnet-4-20250514-v1:0", "Claude Sonnet 4 on Amazon Bedrock"),
    ("bedrock:anthropic.claude-3-5-haiku-20241022-v1:0", "Claude Haiku 3.5 on Amazon Bedrock"),
    ("bedrock:amazon.nova-pro-v1:0", "amazon.nova-pro-v1:0 on Amazon Bedrock"),
])
def test_model_label(name, label):
    assert model_label(name) == label


def test_unknown_scenario_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown demo scenario"):
        make_demo_repo(tmp_path / "x", "nope")
