import { useCallback, useSyncExternalStore } from "react";

import type { PlayerState, ReplayPlayer, Speed } from "./replay";

const noop = () => () => {};

export function usePlayerState(player: ReplayPlayer | null): PlayerState | null {
  const subscribe = useCallback((cb: () => void) => (player ? player.subscribe(cb) : noop()), [player]);
  return useSyncExternalStore(subscribe, () => (player ? player.getState() : null));
}

const STAGE_LABEL: Record<PlayerState["stage"], string> = {
  playing: "",
  review: "Paused for your review",
  finishing: "Preparing the outputs",
  done: "Finished",
};

const SPEEDS: Speed[] = [1, 4];

export function ReplayControls({ player, state }: { player: ReplayPlayer; state: PlayerState }) {
  const playing = state.stage === "playing";
  const label = playing ? `${state.paused ? "Paused at" : "Step"} ${state.position} of ${state.total}` : STAGE_LABEL[state.stage];
  return (
    <div className="controls" role="group" aria-label="Replay controls">
      <button type="button" className="btn btn--small" disabled={!playing} onClick={() => (state.paused ? player.resume() : player.pause())}>
        {state.paused ? "Play" : "Pause"}
      </button>
      <div className="seg" role="group" aria-label="Replay speed">
        {SPEEDS.map((s) => (
          <button key={s} type="button" aria-pressed={state.speed === s} onClick={() => player.setSpeed(s)}>
            {s}x
          </button>
        ))}
      </div>
      <button type="button" className="btn btn--small" disabled={!playing} onClick={() => player.skipToReview()}>
        Skip to review
      </button>
      <button type="button" className="btn btn--small btn--ghost" onClick={() => player.restart()}>
        Restart
      </button>
      <div className="controls__progress">
        <progress max={state.total} value={state.position} aria-label="Replay progress" />
        <span className="muted">{label}</span>
      </div>
    </div>
  );
}
