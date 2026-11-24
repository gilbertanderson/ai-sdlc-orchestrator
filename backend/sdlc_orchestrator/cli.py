"""Command line entry point.

    sdlc-orchestrator serve                       # API + dashboard on http://127.0.0.1:8000
    sdlc-orchestrator run --repo . --base main    # run in the terminal, review interactively
    sdlc-orchestrator run --demo --yes            # sample repo, auto-approve
    sdlc-orchestrator demo-repo ./sample          # create the sample repo to experiment with
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

    from .demo import make_demo_repo
    from .graph import build_graph

    if args.demo:
        repo, base, head = str(make_demo_repo()), "main", "feature/discounts"
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
    from .demo import make_demo_repo

    print(make_demo_repo(args.path))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sdlc-orchestrator", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="prepare a PR from a branch, in the terminal")
    r.add_argument("--repo", default=".")
    r.add_argument("--base", default="main")
    r.add_argument("--head", default="HEAD")
    r.add_argument("--demo", action="store_true", help="use a generated sample repo")
    r.add_argument("--yes", action="store_true", help="approve without prompting")
    r.add_argument("--json", action="store_true", help="print the final report as JSON")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("serve", help="start the API and dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)

    d = sub.add_parser("demo-repo", help="create the sample repository")
    d.add_argument("path")
    d.set_defaults(fn=cmd_demo_repo)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
