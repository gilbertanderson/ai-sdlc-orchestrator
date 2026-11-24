import { useState } from "react";

import type { ReviewDecision, ReviewPayload } from "../types";

interface Props {
  payload: ReviewPayload;
  onSubmit: (d: ReviewDecision) => void;
  busy?: boolean;
}

export function ReviewPanel({ payload, onSubmit, busy }: Props) {
  const s = payload.summary;
  const [title, setTitle] = useState(s?.title ?? "");
  const [note, setNote] = useState("");
  const [dismissed, setDismissed] = useState<Set<string>>(
    () => new Set(payload.findings.filter((f) => f.dismissed).map((f) => f.id)),
  );
  const [includeTests, setIncludeTests] = useState(true);
  const [applyTests, setApplyTests] = useState(false);
  const passing = payload.tests.filter((t) => t.status === "passing");

  const toggle = (id: string) =>
    setDismissed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const submit = (decision: "approve" | "reject") =>
    onSubmit({
      decision,
      title: title !== s?.title ? title : undefined,
      note,
      dismissed: [...dismissed],
      include_tests: includeTests,
      apply_tests: includeTests && applyTests,
    });

  return (
    <section className="panel review" aria-label="Human review">
      <header className="panel__head">
        <h2>Your review</h2>
        <p>The agents are paused. Nothing is written until you approve.</p>
      </header>

      {s && (
        <div className="review__summary">
          <label>
            PR title
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <p>{s.summary}</p>
          {s.risk && (
            <p>
              <span className={`risk risk--${s.risk}`}>{s.risk} risk</span> {s.risk_reasons?.join("; ")}
            </p>
          )}
          {s.changes && (
            <ul className="changes">
              {s.changes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <h3>Security findings ({payload.findings.length})</h3>
      {payload.findings.length === 0 && <p className="muted">No findings.</p>}
      <ul className="findings">
        {payload.findings.map((f) => (
          <li key={f.id} className={dismissed.has(f.id) ? "finding finding--dismissed" : "finding"}>
            <label>
              <input type="checkbox" checked={dismissed.has(f.id)} onChange={() => toggle(f.id)} aria-label={`Dismiss ${f.title}`} />
              <span className={`sev sev--${f.severity}`}>{f.severity}</span>
              <strong>{f.title}</strong>
              <code>
                {f.file}:{f.line}
              </code>
            </label>
            {f.snippet && <pre className="snippet">{f.snippet}</pre>}
            <p className="muted">
              {f.explanation} {f.fix && <>Fix: {f.fix}</>} {f.cwe}
            </p>
          </li>
        ))}
      </ul>
      {payload.findings.length > 0 && <p className="hint">Check a finding to dismiss it as a false positive.</p>}

      <h3>Generated tests</h3>
      {payload.tests.length === 0 && <p className="muted">No tests were generated for this diff.</p>}
      <ul className="tests">
        {payload.tests.map((t) => (
          <li key={t.test_path}>
            <span className={`tstatus tstatus--${t.status}`}>{t.status.replace("_", " ")}</span>
            <code>{t.test_path}</code>
            <span className="muted">
              {Object.entries(t.counts ?? {})
                .map(([k, v]) => `${v} ${k}`)
                .join(", ")}{" "}
              · {t.attempts} attempt{t.attempts === 1 ? "" : "s"}
            </span>
            {t.suspected_bugs && t.suspected_bugs.length > 0 && (
              <p className="bug">Suspected bug in the code: {t.suspected_bugs.join(", ")}</p>
            )}
            <details>
              <summary>View test file</summary>
              <pre>{t.code}</pre>
            </details>
          </li>
        ))}
      </ul>
      {passing.length > 0 && (
        <div className="toggles">
          <label>
            <input type="checkbox" checked={includeTests} onChange={(e) => setIncludeTests(e.target.checked)} />
            Keep the {passing.length} passing test file{passing.length === 1 ? "" : "s"}
          </label>
          <label className={includeTests ? "" : "muted"}>
            <input
              type="checkbox"
              disabled={!includeTests}
              checked={applyTests}
              onChange={(e) => setApplyTests(e.target.checked)}
            />
            Also write them into the repository's working tree
          </label>
        </div>
      )}

      <label className="note">
        Note for the PR (optional)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
      </label>

      <div className="actions">
        <button className="btn btn--primary" disabled={busy} onClick={() => submit("approve")}>
          Approve
        </button>
        <button className="btn btn--ghost" disabled={busy} onClick={() => submit("reject")}>
          Reject
        </button>
      </div>
    </section>
  );
}
