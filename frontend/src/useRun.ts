import { useCallback, useEffect, useReducer } from "react";

import { initialRunView, runReducer } from "./runReducer";
import type { RunSource } from "./transport";
import type { ReviewDecision } from "./types";

/** Follows one run from a source: the local server, or a recorded replay in the browser demo. */
export function useRun(source: RunSource | null) {
  const [view, dispatch] = useReducer(runReducer, initialRunView);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!source) return;
    return source.connect({
      message: (m) => dispatch(m),
      connection: (connected) => dispatch({ type: "connection", connected }),
    });
  }, [source]);

  const sendReview = useCallback((review: ReviewDecision) => source?.sendReview(review), [source]);
  return { ...view, sendReview };
}
