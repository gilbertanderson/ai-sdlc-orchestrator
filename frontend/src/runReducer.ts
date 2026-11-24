import type { RunSnapshot, ServerMessage } from "./types";

export interface RunView {
  run: RunSnapshot | null;
  connected: boolean;
  notice: string | null;
}

export type RunAction = ServerMessage | { type: "connection"; connected: boolean } | { type: "reset" };

export const initialRunView: RunView = { run: null, connected: false, notice: null };

export function runReducer(state: RunView, action: RunAction): RunView {
  switch (action.type) {
    case "reset":
      return initialRunView;
    case "connection":
      return { ...state, connected: action.connected };
    case "snapshot":
      return { ...state, run: action.run, notice: null };
    case "event":
      if (!state.run) return state;
      return { ...state, run: { ...state.run, events: [...state.run.events, action] } };
    case "status":
      if (!state.run) return state;
      return {
        ...state,
        run: {
          ...state.run,
          status: action.status,
          review: action.review ?? state.run.review,
          report: action.report ?? state.run.report,
          error: action.error,
        },
      };
    case "error":
      return { ...state, notice: action.message };
  }
}

/** Latest event per agent, used for the lane headers. */
export function latestByAgent(run: RunSnapshot | null) {
  const out: Record<string, RunSnapshot["events"][number]> = {};
  for (const e of run?.events ?? []) out[e.agent] = e;
  return out;
}
