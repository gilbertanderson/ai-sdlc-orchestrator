import type { Report } from "../types";

export function ReportPanel({ report }: { report: Report }) {
  const approved = report.status === "approved";
  return (
    <section className={`panel report report--${report.status}`} aria-label="Result">
      <header className="panel__head">
        <h2>{approved ? "Approved" : "Rejected"}</h2>
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
          <dt>Files written</dt>
          <dd>{report.files.length}</dd>
        </div>
      </dl>
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
      {report.applied_to_repo && <p>The passing tests were also written into the repository.</p>}
    </section>
  );
}
