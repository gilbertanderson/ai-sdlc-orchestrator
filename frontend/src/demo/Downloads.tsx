import { useEffect, useMemo, useState } from "react";

import { Markdown } from "./Markdown";

const MIME: Record<string, string> = { md: "text/markdown", json: "application/json", py: "text/x-python" };
const mime = (path: string) => `${MIME[path.split(".").pop() ?? ""] ?? "text/plain"};charset=utf-8`;
const fileName = (path: string) => path.split("/").pop() ?? path;

/** The approved run's files, built in the browser, with a preview of the PR description. */
export function Downloads({ files }: { files: Record<string, string> }) {
  const urls = useMemo(
    () => Object.fromEntries(Object.entries(files).map(([path, text]) => [path, URL.createObjectURL(new Blob([text], { type: mime(path) }))])),
    [files],
  );
  useEffect(() => () => Object.values(urls).forEach((u) => URL.revokeObjectURL(u)), [urls]);
  const md = files["PR_DESCRIPTION.md"];
  const [view, setView] = useState<"preview" | "markdown">("preview");
  const [copied, setCopied] = useState(false);
  const canCopy = typeof navigator !== "undefined" && Boolean(navigator.clipboard);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setView("markdown");
    }
  };

  return (
    <div className="downloads">
      <p className="muted">
        Built in your browser by a port of the server's output code, checked against it in CI. Nothing was uploaded.
      </p>
      <ul className="files">
        {Object.keys(files).map((path) => (
          <li key={path}>
            <code>{path}</code>
            <a className="btn btn--small" href={urls[path]} download={fileName(path)}>
              Download<span className="sr-only"> {path}</span>
            </a>
          </li>
        ))}
      </ul>
      {md && (
        <section className="prview" aria-label="PR description">
          <div className="prview__bar">
            <h3>PR description</h3>
            <div className="seg" role="group" aria-label="Show the PR description as">
              <button type="button" aria-pressed={view === "preview"} onClick={() => setView("preview")}>
                Preview
              </button>
              <button type="button" aria-pressed={view === "markdown"} onClick={() => setView("markdown")}>
                Markdown
              </button>
            </div>
            {canCopy && (
              <button type="button" className="btn btn--small" onClick={copy}>
                {copied ? "Copied" : "Copy Markdown"}
              </button>
            )}
          </div>
          {view === "preview" ? <Markdown text={md} /> : <pre className="prview__raw">{md}</pre>}
          <p className="sr-only" aria-live="polite">
            {copied ? "Copied the Markdown to the clipboard" : ""}
          </p>
        </section>
      )}
    </div>
  );
}
