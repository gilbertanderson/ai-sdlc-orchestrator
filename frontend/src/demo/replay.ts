/**
 * Plays a recorded run as if it came from the server, then handles the review in
 * the browser.
 *
 * Messages arrive in their recorded order. The gap before each one is the recorded
 * gap, held between MIN_GAP and MAX_GAP seconds so bursts stay readable and slow
 * steps don't stall, then divided by the speed. On review, the player builds the
 * outputs with the same logic as the backend's `finalize` and answers with the same
 * messages the server sends.
 */
import type { RunHandlers, RunSource } from "../transport";
import type { Report, ReviewDecision, ReviewPayload, ServerMessage } from "../types";
import { prepareOutputs, type PreparedOutputs } from "./outputs";
import { reviewOf, type Recording } from "./types";

export const MIN_GAP = 0.3;
export const MAX_GAP = 1.5;
export const FIRST_GAP = 0.5;
export const REVIEW_STEP = 0.45;

export type Speed = 1 | 4;

export interface PlayerState {
  /** Recorded messages delivered so far. */
  position: number;
  total: number;
  speed: Speed;
  paused: boolean;
  stage: "playing" | "review" | "finishing" | "done";
  outputs: PreparedOutputs | null;
}

interface Options {
  speed?: Speed;
  now?: () => number;
}

let runCounter = 0;

export class ReplayPlayer implements RunSource {
  readonly recording: Recording;
  readonly review: ReviewPayload;
  private handlers: RunHandlers | null = null;
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private listeners = new Set<(s: PlayerState) => void>();
  private now: () => number;
  private created = 0;
  private runId = "";
  private state: PlayerState;

  constructor(recording: Recording, { speed = 1, now = () => Date.now() }: Options = {}) {
    this.recording = recording;
    this.review = reviewOf(recording);
    this.now = now;
    this.state = { position: 0, total: recording.messages.length, speed, paused: false, stage: "playing", outputs: null };
  }

  // ---------------------------------------------------------------- RunSource
  connect(handlers: RunHandlers): () => void {
    this.handlers = handlers;
    this.start();
    return () => {
      this.clearTimers();
      this.handlers = null;
    };
  }

  sendReview(review: ReviewDecision): void {
    if (this.state.stage !== "review") {
      this.send({ type: "error", message: `run is ${this.state.stage === "done" ? "done" : "running"}, not awaiting review` });
      return;
    }
    const outputs = prepareOutputs(this.recording.base_summary, this.review.findings, this.review.tests, review);
    const report: Report = {
      status: outputs.approved ? "approved" : "rejected",
      output_dir: "your browser",
      files: Object.keys(outputs.files),
      applied_to_repo: false,
      summary: outputs.summary as Report["summary"],
      open_findings: outputs.open_findings,
      tests_passing: outputs.tests_passing,
    };
    const verdict = review.decision ?? "approve";
    this.update({ stage: "finishing" });
    this.send({ type: "status", status: "running", review: this.review, report: null, error: null });
    const steps: ServerMessage[] = [
      this.event("review", `Reviewer chose: ${verdict}` + (review.note ? ` (${review.note})` : "")),
      this.event("done", `Run ${report.status}. Prepared ${report.files.length} file(s) in your browser`, { report }),
      { type: "status", status: "done", review: this.review, report, error: null },
    ];
    steps.forEach((m, i) =>
      this.later((REVIEW_STEP * (i + 1)) / this.state.speed, () => {
        // the outputs are ready before the report that lists them arrives
        if (i === steps.length - 1) this.update({ stage: "done", outputs });
        this.send(m);
      }),
    );
  }

  // ----------------------------------------------------------------- controls
  getState(): PlayerState {
    return this.state;
  }

  subscribe(listener: (s: PlayerState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setSpeed(speed: Speed): void {
    this.update({ speed });
    if (this.state.stage === "playing" && !this.state.paused) this.schedule();
  }

  pause(): void {
    if (this.state.stage !== "playing") return;
    this.clearTimers();
    this.update({ paused: true });
  }

  resume(): void {
    if (!this.state.paused) return;
    this.update({ paused: false });
    this.schedule();
  }

  /** Delivers everything up to the review at once. */
  skipToReview(): void {
    if (this.state.stage !== "playing") return;
    this.clearTimers();
    while (this.state.position < this.state.total) this.deliverNext();
  }

  restart(): void {
    if (this.handlers) this.start();
  }

  /** The gap in seconds before message `i` at 1x. */
  gapBefore(i: number): number {
    const msgs = this.recording.messages;
    if (i === 0) return FIRST_GAP;
    const gap = msgs[i].t - msgs[i - 1].t;
    return Math.min(MAX_GAP, Math.max(MIN_GAP, gap));
  }

  // ------------------------------------------------------------------ private
  private start() {
    this.clearTimers();
    this.runId = `${this.recording.id}-${++runCounter}`;
    this.created = this.now() / 1000;
    this.update({ position: 0, paused: false, stage: "playing", outputs: null });
    this.handlers?.connection(true);
    this.send({
      type: "snapshot",
      run: {
        id: this.runId,
        request: this.recording.request,
        status: "running",
        created: this.created,
        events: [],
        review: null,
        report: null,
        error: null,
      },
    });
    this.schedule();
  }

  private schedule() {
    this.clearTimers();
    if (this.state.paused || this.state.position >= this.state.total) return;
    this.later(this.gapBefore(this.state.position) / this.state.speed, () => {
      this.deliverNext();
      this.schedule();
    });
  }

  private deliverNext() {
    const { t, m } = this.recording.messages[this.state.position];
    this.send(m.type === "event" ? { ...m, ts: this.created + t } : m);
    const position = this.state.position + 1;
    this.update({ position, stage: position >= this.state.total ? "review" : "playing" });
  }

  private event(phase: "review" | "done", message: string, data: Record<string, unknown> = {}): ServerMessage {
    return { type: "event", agent: "orchestrator", phase, message, data, ts: this.now() / 1000 };
  }

  private send(m: ServerMessage) {
    this.handlers?.message(m);
  }

  private later(seconds: number, fn: () => void) {
    const id = setTimeout(() => {
      this.timers.delete(id);
      fn();
    }, seconds * 1000);
    this.timers.add(id);
  }

  private clearTimers() {
    for (const id of this.timers) clearTimeout(id);
    this.timers.clear();
  }

  private update(patch: Partial<PlayerState>) {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l(this.state);
  }
}
