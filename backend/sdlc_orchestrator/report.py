"""Rendering the approved run as a PR description."""

from __future__ import annotations

SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}


def render_pr_description(summary: dict, findings: list[dict], test_jobs: list[dict], note: str = "") -> str:
    s = summary or {}
    out = [f"# {s.get('title', 'Pull request')}", "", s.get("summary", ""), ""]
    if s.get("changes"):
        out += ["## Changes", *[f"- {c}" for c in s["changes"]], ""]
    risk = s.get("risk")
    if risk:
        out += [f"## Risk: {risk}", *[f"- {r}" for r in s.get("risk_reasons", [])], ""]

    open_findings = [f for f in findings if not f.get("dismissed")]
    out.append("## Security review")
    if open_findings:
        out += ["| Severity | Finding | Location | Fix |", "|---|---|---|---|"]
        for f in open_findings:
            loc = f"`{f['file']}:{f['line']}`" if f.get("file") else ""
            out.append(f"| {SEVERITY_ICON.get(f['severity'], '')} {f['severity']} | {f['title']} ({f.get('cwe', '')}) | {loc} | {f.get('fix', '')} |")
    else:
        out.append("No open findings.")
    dismissed = len(findings) - len(open_findings)
    if dismissed:
        out.append(f"\n_{dismissed} finding(s) reviewed and dismissed._")
    out.append("")

    if test_jobs:
        out.append("## Generated tests")
        for j in test_jobs:
            counts = ", ".join(f"{v} {k}" for k, v in (j.get("counts") or {}).items())
            out.append(f"- `{j['test_path']}` for `{j['file']}`: {j['status']}" + (f" ({counts})" if counts else "")
                       + f", {j['attempts']} attempt(s)")
            for bug in j.get("suspected_bugs") or []:
                out.append(f"  - Suspected bug: `{bug}`")
        out.append("")

    if s.get("testing_notes"):
        out += ["## How to test", *[f"- {t}" for t in s["testing_notes"]], ""]
    if s.get("reviewer_checklist"):
        out += ["## Reviewer checklist", *[f"- [ ] {c}" for c in s["reviewer_checklist"]], ""]
    if note:
        out += ["## Reviewer note", note, ""]
    out.append("_Prepared by PreReviewer and approved by a human reviewer._")
    return "\n".join(out) + "\n"
