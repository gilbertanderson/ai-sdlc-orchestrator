import { Fragment, useMemo } from "react";

import type { Finding } from "../types";
import { parseDiff } from "./diff";

interface Props {
  diff: string;
  commits: string[];
  findings: Finding[];
}

const SIGN = { add: "+", del: "-", ctx: " ", hunk: "", meta: "" } as const;
const SPOKEN = { add: "Added: ", del: "Removed: ", ctx: "", hunk: "", meta: "" } as const;

/** The branch's diff, with lines that have open security findings marked once the agents have reported. */
export function DiffView({ diff, commits, findings }: Props) {
  const files = useMemo(() => parseDiff(diff), [diff]);
  const flags = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of findings) {
      if (f.dismissed || !f.file) continue;
      const key = `${f.file}:${f.line}`;
      map.set(key, [...(map.get(key) ?? []), f]);
    }
    return map;
  }, [findings]);
  const adds = files.reduce((n, f) => n + f.additions, 0);
  const dels = files.reduce((n, f) => n + f.deletions, 0);
  const marked = [...flags.values()].reduce((n, fs) => n + fs.length, 0);

  return (
    <details className="panel diffview">
      <summary>
        <span className="diffview__title">The diff under review</span>
        <span className="muted">
          {files.length} file{files.length === 1 ? "" : "s"}, +{adds} −{dels}, {commits.length} commit{commits.length === 1 ? "" : "s"}
          {marked > 0 && `, ${marked} finding${marked === 1 ? "" : "s"} marked`}
        </span>
      </summary>
      {commits.length > 0 && (
        <ol className="commits" aria-label="Commits, oldest first">
          {[...commits].reverse().map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
      )}
      {files.map((file) => (
        <section key={file.path} className="dfile" aria-label={file.path}>
          <h3 className="dfile__head">
            <code>{file.path}</code>
            <span className={`dstatus dstatus--${file.status}`}>{file.status}</span>
            <span className="muted">
              +{file.additions} −{file.deletions}
            </span>
          </h3>
          <div className="dlines" tabIndex={0} role="group" aria-label={`Changes to ${file.path}`}>
            {file.lines.map((line, i) => {
              const hits = line.kind === "add" ? flags.get(`${file.path}:${line.newNo}`) : undefined;
              return (
                <Fragment key={i}>
                  <div className={`dl dl--${line.kind}${hits ? " dl--flag" : ""}`}>
                    <span className="dl__no" aria-hidden>
                      {line.newNo ?? ""}
                    </span>
                    <span className="dl__sign" aria-hidden>
                      {SIGN[line.kind]}
                    </span>
                    <code className="dl__code">
                      <span className="sr-only">{SPOKEN[line.kind]}</span>
                      {line.text || " "}
                    </code>
                  </div>
                  {hits?.map((f) => (
                    <div key={f.id} className="dl__note">
                      <span className={`sev sev--${f.severity}`}>{f.severity}</span> {f.title} <span className="muted">line {f.line}</span>
                    </div>
                  ))}
                </Fragment>
              );
            })}
          </div>
        </section>
      ))}
    </details>
  );
}
