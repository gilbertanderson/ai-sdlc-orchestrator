import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type RunListItem } from "./api";
import { AgentLanes } from "./components/AgentLanes";
import { ReportPanel } from "./components/ReportPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { serverSource } from "./transport";
import type { RunSnapshot } from "./types";
import { useRun } from "./useRun";

const STATUS_LABEL: Record<RunSnapshot["status"], string> = {
  running: "Agents working",
  awaiting_review: "Needs your review",
  done: "Finished",
  error: "Failed",
};

export default function App() {
  const [model, setModel] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [form, setForm] = useState({ repo: "", base: "main", head: "HEAD" });
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const source = useMemo(() => (selected ? serverSource(selected) : null), [selected]);
  const { run, connected, notice, sendReview } = useRun(source);

  const refresh = useCallback(() => api.listRuns().then(setRuns).catch(() => {}), []);

  useEffect(() => {
    api.health().then((h) => setModel(h.model)).catch(() => setModel(null));
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (run?.status) refresh();
  }, [run?.status, refresh]);

  const start = async (body: Parameters<typeof api.startRun>[0]) => {
    setError(null);
    setStarting(true);
    try {
      const { id } = await api.startRun(body);
      setSelected(id);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <span className="brand__mark" aria-hidden />
          <div>
            <h1>Patchwise</h1>
            <p className="muted">{model ? `Model: ${model}` : "API offline"}</p>
          </div>
        </div>

        <button className="btn btn--primary btn--block" disabled={starting} onClick={() => start({ demo: true })}>
          Run the demo
        </button>

        <form
          className="newrun"
          onSubmit={(e) => {
            e.preventDefault();
            start({ repo: form.repo, base: form.base, head: form.head });
          }}
        >
          <h2>Prepare a PR</h2>
          <label>
            Local repository
            <input required placeholder="/path/to/repo" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} />
          </label>
          <div className="row">
            <label>
              Base
              <input value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value })} />
            </label>
            <label>
              Head
              <input value={form.head} onChange={(e) => setForm({ ...form, head: e.target.value })} />
            </label>
          </div>
          <button className="btn btn--block" disabled={starting}>
            Start run
          </button>
          {error && <p className="error">{error}</p>}
        </form>

        <h2>Runs</h2>
        <ul className="runs">
          {runs.length === 0 && <li className="muted">No runs yet</li>}
          {runs.map((r) => (
            <li key={r.id}>
              <button className={r.id === selected ? "runlink runlink--active" : "runlink"} onClick={() => setSelected(r.id)}>
                <span className={`dot dot--${r.status}`} aria-hidden />
                <span>
                  {r.request.demo ? "Demo" : (r.request.repo ?? "diff").split("/").pop()} · {r.request.head}
                  <small>{new Date(r.created * 1000).toLocaleTimeString()}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="main">
        {!run && (
          <div className="empty">
            <h2>Agentic PR preparation with a human in the loop</h2>
            <p>
              A planner reads your branch's diff and dispatches agents that write the PR description, generate and run unit
              tests, and scan for security issues. You watch their reasoning live, then approve, edit or reject before
              anything is written.
            </p>
            <p className="muted">Start with the demo: a small invoicing repo with a real bug and a few security issues.</p>
          </div>
        )}
        {run && (
          <>
            <header className="runhead">
              <div>
                <h2>
                  {run.request.demo ? "Demo repository" : run.request.repo ?? "Diff"} <span className="muted">{run.request.base}…{run.request.head}</span>
                </h2>
                <p className="muted">
                  Run {run.id} · {connected ? "live" : "reconnecting"}
                </p>
              </div>
              <span className={`status status--${run.status}`}>{STATUS_LABEL[run.status]}</span>
            </header>
            {notice && <p className="error">{notice}</p>}
            {run.error && <p className="error">{run.error}</p>}
            <AgentLanes run={run} />
            {run.status === "awaiting_review" && run.review && (
              <ReviewPanel key={run.id} payload={run.review} onSubmit={sendReview} />
            )}
            {run.report && <ReportPanel report={run.report} />}
          </>
        )}
      </main>
    </div>
  );
}
