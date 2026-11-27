/**
 * The browser's port of the backend's output logic: `prepare_outputs`,
 * `with_security_risk` (graph.py) and `render_pr_description` (report.py).
 *
 * The demo has no server, so when a visitor approves a recorded run, this builds the
 * same PR description, test files and security report that `finalize` would write.
 * outputs.test.ts checks it against golden files that Python generates from the same
 * recordings, so keep it in step with the Python code.
 */
import type { Finding, ReviewDecision, Summary, TestJob } from "../types";

type ReviewInput = Partial<ReviewDecision> & { title?: string | null };
type SummaryInput = Partial<Summary>;
type TestInput = Pick<TestJob, "file" | "test_path" | "status" | "attempts" | "code" | "counts" | "suspected_bugs">;

export interface PreparedOutputs {
  approved: boolean;
  summary: SummaryInput;
  findings: Finding[];
  /** File path -> content, in the order `finalize` writes them. */
  files: Record<string, string>;
  open_findings: number;
  tests_passing: number;
}

const SEVERITY_ICON: Record<string, string> = { critical: "🔴", high: "🟠", medium: "🟡", low: "⚪" };

/** Formats a value the way Python's str() would, for the values these files contain. */
function py(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  return String(value);
}

/** Python's dict.get: the value when the key is present, even if it is null. */
function get<T extends object>(obj: T, key: string, fallback: unknown): unknown {
  return Object.prototype.hasOwnProperty.call(obj, key) ? (obj as Record<string, unknown>)[key] : fallback;
}

const truthy = (v: unknown) => (Array.isArray(v) ? v.length > 0 : Boolean(v));

/** `json.dumps(value, indent=2)`: same layout as JSON.stringify, with non-ASCII escaped. */
export function pythonJsonDumps(value: unknown): string {
  return JSON.stringify(value, null, 2).replace(
    /[\u007f-￿]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}

export function withSecurityRisk(summary: SummaryInput, findings: Finding[], dismissed: Set<string>): SummaryInput {
  const serious = findings.filter(
    (f) => !f.dismissed && !dismissed.has(f.id) && (f.severity === "critical" || f.severity === "high"),
  );
  if (serious.length === 0 || Object.keys(summary).length === 0) return summary;
  return {
    ...summary,
    risk: "high",
    risk_reasons: [...((get(summary, "risk_reasons", []) as string[]) ?? []), `${serious.length} open critical or high security finding(s)`],
  };
}

export function renderPrDescription(summary: SummaryInput, findings: Finding[], testJobs: TestInput[], note = ""): string {
  const s = summary ?? {};
  const out: string[] = [`# ${py(get(s, "title", "Pull request"))}`, "", py(get(s, "summary", "")), ""];
  if (truthy(s.changes)) out.push("## Changes", ...s.changes!.map((c) => `- ${c}`), "");
  if (truthy(s.risk)) out.push(`## Risk: ${s.risk}`, ...((get(s, "risk_reasons", []) as string[]) ?? []).map((r) => `- ${r}`), "");

  const open = findings.filter((f) => !f.dismissed);
  out.push("## Security review");
  if (open.length > 0) {
    out.push("| Severity | Finding | Location | Fix |", "|---|---|---|---|");
    for (const f of open) {
      const loc = truthy(f.file) ? `\`${f.file}:${f.line}\`` : "";
      out.push(`| ${SEVERITY_ICON[f.severity] ?? ""} ${f.severity} | ${f.title} (${py(get(f, "cwe", ""))}) | ${loc} | ${py(get(f, "fix", ""))} |`);
    }
  } else {
    out.push("No open findings.");
  }
  const dismissed = findings.length - open.length;
  if (dismissed) out.push(`\n_${dismissed} finding(s) reviewed and dismissed._`);
  out.push("");

  if (testJobs.length > 0) {
    out.push("## Generated tests");
    for (const j of testJobs) {
      const counts = Object.entries(j.counts ?? {})
        .map(([k, v]) => `${v} ${k}`)
        .join(", ");
      out.push(`- \`${j.test_path}\` for \`${j.file}\`: ${j.status}` + (counts ? ` (${counts})` : "") + `, ${j.attempts} attempt(s)`);
      for (const bug of j.suspected_bugs ?? []) out.push(`  - Suspected bug: \`${bug}\``);
    }
    out.push("");
  }

  if (truthy(s.testing_notes)) out.push("## How to test", ...s.testing_notes!.map((t) => `- ${t}`), "");
  if (truthy(s.reviewer_checklist)) out.push("## Reviewer checklist", ...s.reviewer_checklist!.map((c) => `- [ ] ${c}`), "");
  if (note) out.push("## Reviewer note", note, "");
  out.push("_Prepared by AI-Native SDLC Orchestrator and approved by a human reviewer._");
  return out.join("\n") + "\n";
}

export function prepareOutputs(
  summary: SummaryInput | null | undefined,
  findings: Finding[],
  testJobs: TestInput[],
  review: ReviewInput,
): PreparedOutputs {
  const approved = (review.decision ?? "approve") === "approve";
  const dismissed = new Set(review.dismissed ?? []);
  let finalSummary = withSecurityRisk({ ...(summary ?? {}) }, findings, dismissed);
  if (review.title) finalSummary = { ...finalSummary, title: review.title };
  const finalFindings = findings.map((f) => ({ ...f, dismissed: Boolean(f.dismissed) || dismissed.has(f.id) }));
  const includeTests = approved && (review.include_tests ?? true);
  const tests = includeTests ? testJobs.filter((j) => j.status === "passing") : [];

  const files: Record<string, string> = {};
  if (approved) {
    files["PR_DESCRIPTION.md"] = renderPrDescription(finalSummary, finalFindings, testJobs, review.note ?? "");
    for (const j of tests) files[j.test_path] = j.code;
  }
  files["security-report.json"] = pythonJsonDumps(finalFindings);
  return {
    approved,
    summary: finalSummary,
    findings: finalFindings,
    files,
    open_findings: finalFindings.filter((f) => !f.dismissed).length,
    tests_passing: testJobs.filter((j) => j.status === "passing").length,
  };
}
