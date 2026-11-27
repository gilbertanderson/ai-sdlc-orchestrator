import type { AgentEvent, ReviewDecision, ReviewPayload, RunSnapshot, ServerMessage, Summary } from "../types";

/** An agent event as recorded: the player stamps `ts` when it plays the event. */
export type RecordedEvent = Omit<AgentEvent, "ts">;
export type RecordedStatus = Extract<ServerMessage, { type: "status" }>;

export interface RecordedMessage {
  /** Seconds after the run started. */
  t: number;
  m: RecordedEvent | RecordedStatus;
}

/** A real run saved by `sdlc-orchestrator record`, up to the human review. */
export interface Recording {
  format: 1;
  id: string;
  scenario: string;
  title: string;
  blurb: string;
  order: number;
  model: string;
  model_label: string;
  recorded_at: string;
  duration_s: number;
  request: RunSnapshot["request"];
  commits: string[];
  diff: string;
  /** The summary as the agent wrote it, before open findings raised the risk. */
  base_summary: Partial<Summary>;
  messages: RecordedMessage[];
}

export type RecordingInfo = Pick<
  Recording,
  "id" | "scenario" | "title" | "blurb" | "order" | "model" | "model_label" | "recorded_at" | "duration_s"
> & { file: string };

export interface RecordingIndex {
  format: 1;
  runs: RecordingInfo[];
}

/** The review payload a recording pauses on. */
export function reviewOf(recording: Recording): ReviewPayload {
  const last = recording.messages[recording.messages.length - 1]?.m;
  if (!last || last.type !== "status" || !last.review) throw new Error(`Recording ${recording.id} does not end at a review`);
  return last.review;
}

export interface GoldenCase {
  name: string;
  review: ReviewDecision & { title?: string | null };
  expected: {
    approved: boolean;
    summary: Partial<Summary>;
    findings: ReviewPayload["findings"];
    files: Record<string, string>;
    open_findings: number;
    tests_passing: number;
  };
}

export interface Golden {
  format: 1;
  id: string;
  cases: GoldenCase[];
}
