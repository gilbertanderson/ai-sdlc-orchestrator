import { useEffect, useRef, type ReactNode } from "react";

import type { Report } from "../types";

interface Props {
  report: Report;
  /** Shown in place of the server's output folder, e.g. the browser demo's downloads. */
  children?: ReactNode;
  /** Move focus to the result when it appears, since the review buttons that had it are gone. */
  focusOnMount?: boolean;
}

export function ReportPanel({ report, children, focusOnMount }: Props) {
  const approved = report.status === "approved";
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focusOnMount) heading.current?.focus();
  }, [focusOnMount]);

  return (
    <section className={`panel report report--${report.status}`} aria-label="Result">
      <header className="panel__head">
        <h2 ref={heading} tabIndex={-1}>
          {approved ? "Approved" : "Rejected"}
        </h2>
        <p>{report.summary?.title}</p>
      </header>
      <dl className="stats">
        <div>
          <dt>Open findings</dt>
          <dd>{report.open_findings}</dd>
        </div>
        <div>
          <dt>Passing test files</dt>
          <dd>{report.tests_passing}</dd>
        </div>
        <div>
          <dt>{children ? "Files ready" : "Files written"}</dt>
          <dd>{report.files.length}</dd>
        </div>
      </dl>
      {children ?? (
        <>
          <p className="muted">
            Output folder: <code>{report.output_dir}</code>
          </p>
          <ul className="files">
            {report.files.map((f) => (
              <li key={f}>
                <code>{f}</code>
              </li>
            ))}
          </ul>
        </>
      )}
      {report.applied_to_repo && <p>The passing tests were also written into the repository.</p>}
    </section>
  );
}
