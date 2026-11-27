import { initialRunView, runReducer, type RunView } from "../runReducer";
import type { ServerMessage } from "../types";
import { FIRST_GAP, MAX_GAP, MIN_GAP, ReplayPlayer } from "./replay";
import { reviewOf, type Recording } from "./types";

const recordings = import.meta.glob<Recording>("../../public/runs/*.json", { eager: true, import: "default" });
const invoicing = Object.values(recordings).find((r) => r.id === "invoicing")!;

function harness(recording: Recording = invoicing, speed: 1 | 4 = 1) {
  const player = new ReplayPlayer(recording, { speed, now: () => 1_000_000 });
  const messages: ServerMessage[] = [];
  let view: RunView = initialRunView;
  const stop = player.connect({
    message: (m) => {
      messages.push(m);
      view = runReducer(view, m);
    },
    connection: (connected) => (view = runReducer(view, { type: "connection", connected })),
  });
  return { player, messages, stop, view: () => view };
}

const totalSeconds = (p: ReplayPlayer) => p.recording.messages.reduce((sum, _m, i) => sum + p.gapBefore(i), 0);

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ReplayPlayer", () => {
  it("sends a snapshot, then every recorded message, and pauses at the review", () => {
    const { player, messages, view } = harness();
    expect(messages[0].type).toBe("snapshot");
    expect(view().connected).toBe(true);
    vi.advanceTimersByTime(FIRST_GAP * 1000 - 1);
    expect(messages).toHaveLength(1);

    vi.advanceTimersByTime(totalSeconds(player) * 1000);
    expect(messages).toHaveLength(invoicing.messages.length + 1);
    const run = view().run!;
    expect(run.status).toBe("awaiting_review");
    expect(run.events).toHaveLength(invoicing.messages.length - 1);
    // events are stamped relative to when the replay started
    expect(run.events[0].ts).toBeCloseTo(1000 + invoicing.messages[0].t);
    expect(run.review).toEqual(reviewOf(invoicing));
    expect(player.getState()).toMatchObject({ stage: "review", position: invoicing.messages.length });
  });

  it("keeps gaps readable and caps slow steps", () => {
    const { player } = harness();
    const gaps = invoicing.messages.map((_m, i) => player.gapBefore(i));
    expect(Math.min(...gaps)).toBeGreaterThanOrEqual(MIN_GAP);
    expect(Math.max(...gaps)).toBeLessThanOrEqual(MAX_GAP);
  });

  it("plays four times faster at 4x", () => {
    const { player, view } = harness(invoicing, 4);
    vi.advanceTimersByTime((totalSeconds(player) * 1000) / 4 + 1);
    expect(view().run!.status).toBe("awaiting_review");
  });

  it("pauses, resumes, skips to the review and restarts", () => {
    const { player, view, messages } = harness();
    vi.advanceTimersByTime(FIRST_GAP * 1000);
    player.pause();
    const seen = messages.length;
    vi.advanceTimersByTime(60_000);
    expect(messages).toHaveLength(seen);
    player.resume();
    player.skipToReview();
    expect(view().run!.status).toBe("awaiting_review");

    player.restart();
    expect(view().run!.events).toHaveLength(0);
    expect(view().run!.status).toBe("running");
    expect(player.getState().stage).toBe("playing");
  });

  it("approves in the browser with the backend's outputs and messages", () => {
    const { player, view, messages } = harness();
    player.skipToReview();
    const secret = reviewOf(invoicing).findings.find((f) => f.rule === "SEC003")!;
    player.sendReview({ decision: "approve", note: "ok", dismissed: [secret.id], include_tests: true, apply_tests: false });
    expect(view().run!.status).toBe("running");
    vi.advanceTimersByTime(5_000);

    const run = view().run!;
    expect(run.status).toBe("done");
    expect(run.events.slice(-2).map((e) => e.message)).toEqual([
      "Reviewer chose: approve (ok)",
      "Run approved. Prepared 4 file(s) in your browser",
    ]);
    expect(run.report).toMatchObject({ status: "approved", open_findings: 3, tests_passing: 2, applied_to_repo: false });
    const outputs = player.getState().outputs!;
    expect(Object.keys(outputs.files)).toEqual(run.report!.files);
    expect(outputs.files["PR_DESCRIPTION.md"]).not.toContain("Hardcoded password");

    player.sendReview({ decision: "approve", note: "", dismissed: [], include_tests: true, apply_tests: false });
    expect(messages.at(-1)).toEqual({ type: "error", message: "run is done, not awaiting review" });
  });

  it("rejects a review while the agents are still working", () => {
    const { player, messages } = harness();
    player.sendReview({ decision: "reject", note: "", dismissed: [], include_tests: true, apply_tests: false });
    expect(messages.at(-1)).toEqual({ type: "error", message: "run is running, not awaiting review" });
  });

  it("stops sending when disconnected", () => {
    const { stop, messages } = harness();
    stop();
    vi.advanceTimersByTime(60_000);
    expect(messages).toHaveLength(1);
  });
});
