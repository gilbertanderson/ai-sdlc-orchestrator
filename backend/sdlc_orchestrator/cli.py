"""Command line entry point.

    sdlc-orchestrator serve                       # API + dashboard on http://127.0.0.1:8000
    sdlc-orchestrator run --repo . --base main    # run in the terminal, review interactively
    sdlc-orchestrator run --demo --yes            # sample repo, auto-approve
    sdlc-orchestrator demo-repo ./sample          # create the sample repo to experiment with
    sdlc-orchestrator record --out-dir ../frontend/public/runs   # record runs for the browser demo
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

PHASE_COLOR = {"plan": "36", "observe": "34", "execute": "35", "done": "32", "review": "33", "error": "31"}


def _print_event(e: dict) -> None:
    color = PHASE_COLOR.get(e["phase"], "0")
    tag = f"\033[{color}m{e['agent']:>12} {e['phase']:<8}\033[0m" if sys.stdout.isatty() else f"{e['agent']:>12} {e['phase']:<8}"
    print(f"{tag} {e['message']}")


def _review_in_terminal(payload: dict, auto: bool) -> dict:
    s = payload.get("summary") or {}
    print("\n" + "=" * 72)
    print(f"Title: {s.get('title')}\nRisk:  {s.get('risk')}\n\n{s.get('summary', '')}\n")
    findings = [f for f in payload.get("findings", []) if not f.get("dismissed")]
    for i, f in enumerate(findings, 1):
        print(f"  [{i}] {f['severity']:<8} {f['title']}  {f['file']}:{f['line']}")
    for t in payload.get("tests", []):
        print(f"  tests  {t['file']}: {t['status']} after {t['attempts']} attempt(s)")
    print("=" * 72)
    if auto:
        return {"decision": "approve"}
    answer = input("Approve? [y]es / [n]o / numbers of findings to dismiss, e.g. '2 3': ").strip().lower()
    if answer in {"n", "no"}:
        return {"decision": "reject", "note": input("Reason: ").strip()}
    dismissed = [findings[int(x) - 1]["id"] for x in answer.split() if x.isdigit() and 0 < int(x) <= len(findings)]
    return {"decision": "approve", "dismissed": dismissed, "note": input("Note for the PR (optional): ").strip()}


def cmd_run(args: argparse.Namespace) -> int:
    from langgraph.types import Command

    from .demo import get_scenario, make_demo_repo
    from .graph import build_graph

    if args.demo:
        spec = get_scenario(args.scenario)
        repo, base, head = str(make_demo_repo(None, spec.id)), spec.base, spec.head
        print(f"Sample repo: {repo}")
    else:
        repo, base, head = args.repo, args.base, args.head
    graph = build_graph()
    run_id = uuid.uuid4().hex[:10]
    cfg = {"configurable": {"thread_id": run_id}}
    graph_input: object = {"run_id": run_id, "repo": repo, "base": base, "head": head}
    while True:
        payload = None
        for mode, chunk in graph.stream(graph_input, cfg, stream_mode=["custom", "updates"]):
            if mode == "custom":
                _print_event(chunk)
            elif "__interrupt__" in chunk:
                payload = chunk["__interrupt__"][0].value
            elif "finalize" in chunk:
                report = chunk["finalize"]["report"]
                if args.json:
                    print(json.dumps(report, indent=2))
                return 0 if report["status"] == "approved" else 1
        if payload is None:
            return 0
        graph_input = Command(resume=_review_in_terminal(payload, args.yes))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def cmd_demo_repo(args: argparse.Namespace) -> int:
    from .demo import get_scenario, make_demo_repo

    spec = get_scenario(args.scenario)
    print(f"{make_demo_repo(args.path, spec.id)}  (compare {spec.base}...{spec.head})")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .demo import SCENARIOS
    from .record import public_warnings, record, write_recording

    status = 0
    for scenario in args.scenario or list(SCENARIOS):
        recording, golden = record(scenario)
        path = write_recording(recording, golden, Path(args.out_dir), Path(args.golden_dir) if args.golden_dir else None)
        print(f"Recorded {recording['id']} with {recording['model_label']}: "
              f"{len(recording['messages'])} messages over {recording['duration_s']:.1f} s -> {path}")
        for warning in public_warnings(recording):
            print(f"  check before publishing: {warning}", file=sys.stderr)
            status = 1
    return status


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sdlc-orchestrator", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="prepare a PR from a branch, in the terminal")
    r.add_argument("--repo", default=".")
    r.add_argument("--base", default="main")
    r.add_argument("--head", default="HEAD")
    r.add_argument("--demo", action="store_true", help="use a generated sample repo")
    r.add_argument("--scenario", default="invoicing", help="which sample repo to use with --demo")
    r.add_argument("--yes", action="store_true", help="approve without prompting")
    r.add_argument("--json", action="store_true", help="print the final report as JSON")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("serve", help="start the API and dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)

    d = sub.add_parser("demo-repo", help="create the sample repository")
    d.add_argument("path")
    d.add_argument("--scenario", default="invoicing", help="invoicing (a bug and security issues) or clean")
    d.set_defaults(fn=cmd_demo_repo)

    rec = sub.add_parser("record", help="record demo runs for the browser dashboard")
    rec.add_argument("--scenario", action="append", help="scenario to record; repeat for more (default: all)")
    rec.add_argument("--out-dir", required=True, help="where the recordings and index.json go")
    rec.add_argument("--golden-dir", help="where to save golden outputs for the frontend tests")
    rec.set_defaults(fn=cmd_record)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
