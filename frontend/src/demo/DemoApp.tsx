import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentLanes } from "../components/AgentLanes";
import { ReportPanel } from "../components/ReportPanel";
import { ReviewPanel } from "../components/ReviewPanel";
import type { RunSnapshot } from "../types";
import { useRun } from "../useRun";
import { DiffView } from "./DiffView";
import { Downloads } from "./Downloads";
import { ReplayControls, usePlayerState } from "./ReplayControls";
import { ReplayPlayer } from "./replay";
import type { Recording, RecordingIndex, RecordingInfo } from "./types";

export const REPO_URL = "https://github.com/gilbertanderson/ai-sdlc-orchestrator";
const SITE_URL = "https://gilbertanderson.com/";

const STATUS_LABEL: Record<RunSnapshot["status"], string> = {
  running: "Agents working",
  awaiting_review: "Needs your review",
  done: "Finished",
  error: "Failed",
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(import.meta.env.BASE_URL + path);
  if (!res.ok) throw new Error(`Couldn't load ${path} (${res.status})`);
  return (await res.json()) as T;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

const modelText = (r: Recording) => (r.model === "offline-heuristics" ? "the offline heuristic model" : r.model_label);

const seconds = (s: number) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;

export default function DemoApp() {
  const [runs, setRuns] = useState<RecordingInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [playCount, setPlayCount] = useState(0);
  const [loading, setLoading] = useState<string | null>(null);
  const cache = useRef(new Map<string, Recording>());

  // a fresh player for every pick, so picking the same run again replays it
  const player = useMemo(() => (recording ? new ReplayPlayer(recording) : null), [recording, playCount]);
  const state = usePlayerState(player);
  const { run, notice, sendReview } = useRun(player);

  useEffect(() => {
    if (player && prefersReducedMotion()) player.skipToReview();
  }, [player]);

  const open = useCallback(
    async (info: RecordingInfo) => {
      setError(null);
      setLoading(info.id);
      try {
        const rec = cache.current.get(info.id) ?? (await getJson<Recording>(`runs/${info.file}`));
        cache.current.set(info.id, rec);
        setRecording(rec);
        setPlayCount((n) => n + 1);
        window.history.replaceState(null, "", `?run=${encodeURIComponent(info.id)}`);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(null);
      }
    },
    [],
  );

  useEffect(() => {
    document.title = "Patchwise · Live demo";
    getJson<RecordingIndex>("runs/index.json")
      .then((index) => {
        setRuns(index.runs);
        const wanted = new URLSearchParams(window.location.search).get("run");
        const info = index.runs.find((r) => r.id === wanted);
        if (info) void open(info);
      })
      .catch((e: Error) => setError(e.message));
  }, [open]);

  const announcement = useMemo(() => {
    if (!run || !recording) return "";
    if (run.status === "awaiting_review") return "The agents are done. Your review is ready below.";
    if (run.status === "done" && run.report) return run.report.status === "approved" ? "Approved. The files are ready to download." : "Rejected.";
    if (run.status === "error") return "The run failed.";
    return `Replaying: ${recording.title}`;
  }, [run, recording]);

  const featured = runs?.[0];
  const findings = run?.review?.findings ?? [];

  return (
    <div className="app app--demo">
      <aside className="side">
        <div className="brand">
          <span className="brand__mark" aria-hidden />
          <div>
            <h1>Patchwise</h1>
            <p className="muted">Live demo · recorded runs</p>
          </div>
        </div>

        <nav className="scenarios" aria-label="Recorded runs">
          <h2>Recorded runs</h2>
          {!runs && !error && <p className="muted">Loading…</p>}
          <ul>
            {runs?.map((info) => {
              const active = recording?.id === info.id;
              return (
                <li key={info.id}>
                  <button
                    type="button"
                    className="scenario"
                    aria-current={active ? "true" : undefined}
                    disabled={loading !== null}
                    onClick={() => open(info)}
                  >
                    <span className="scenario__title">{info.title}</span>
                    <span className="scenario__blurb">{info.blurb}</span>
                    <span className="scenario__meta">{info.model_label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      <main className="main">
        <p className="banner" role="note">
          <strong>Demo:</strong> recordings of real runs of the agents, replayed in your browser. Your review is handled
          here too, and nothing leaves this page.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!run && (
          <section className="intro" aria-labelledby="intro-title">
            <h2 id="intro-title">Agentic PR preparation with a human in the loop</h2>
            <p>
              A planner reads a branch's diff and sends work to three agents: one writes the PR description, one generates
              and runs unit tests, and one scans the change for security issues. You watch their reasoning as they work,
              then approve, edit or reject the result before anything is written.
            </p>
            <p className="muted">
              Each run here was recorded from the code in the repo and replays at reading pace. The review at the end is
              yours: edit the title, dismiss findings, then download what the agents prepared.
            </p>
            {featured && (
              <button type="button" className="btn btn--primary intro__start" disabled={loading !== null} onClick={() => open(featured)}>
                Watch a run: {featured.title.charAt(0).toLowerCase() + featured.title.slice(1)}
              </button>
            )}
          </section>
        )}

        {run && recording && player && state && (
          <>
            <header className="runhead">
              <div>
                <h2>{recording.title}</h2>
                <p className="muted">
                  <code>
                    {recording.request.base}…{recording.request.head}
                  </code>{" "}
                  · recorded with {modelText(recording)} · {seconds(recording.duration_s)} of agent work, replayed at
                  reading pace
                </p>
              </div>
              <span className={`status status--${run.status}`}>{STATUS_LABEL[run.status]}</span>
            </header>
            <ReplayControls player={player} state={state} />
            {run.status === "awaiting_review" && (
              <button
                type="button"
                className="btn btn--primary jump"
                onClick={() => {
                  const target = document.getElementById("review");
                  target?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
                  target?.focus({ preventScroll: true });
                }}
              >
                The agents are done. Go to your review
              </button>
            )}
            {notice && <p className="error">{notice}</p>}
            {run.error && <p className="error">{run.error}</p>}
            <DiffView diff={recording.diff} commits={recording.commits} findings={findings} />
            <AgentLanes run={run} />
            {run.status === "awaiting_review" && run.review && (
              <div id="review" tabIndex={-1} className="review-anchor">
                <ReviewPanel key={run.id} payload={run.review} onSubmit={sendReview} canApplyTests={false} />
              </div>
            )}
            {run.report && (
              <ReportPanel report={run.report} focusOnMount>
                <Downloads files={state.outputs?.files ?? {}} />
              </ReportPanel>
            )}
          </>
        )}
        <p className="sr-only" aria-live="polite">
          {announcement}
        </p>
      </main>

      <footer className="side__foot">
        <a className="btn btn--block" href={REPO_URL}>
          Run it yourself on GitHub
        </a>
        <p className="muted">
          Locally it runs the same agents on your own branches, with the offline model or Claude on Amazon Bedrock.
        </p>
        <a className="backlink" href={SITE_URL}>
          Back to gilbertanderson.com
        </a>
      </footer>
    </div>
  );
}
