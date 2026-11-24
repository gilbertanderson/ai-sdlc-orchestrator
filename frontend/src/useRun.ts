import { useEffect, useReducer, useRef } from "react";

import { socketUrl } from "./api";
import { initialRunView, runReducer } from "./runReducer";
import type { ReviewDecision, ServerMessage } from "./types";

/** Subscribes to one run over WebSocket and reconnects if the socket drops mid-run. */
export function useRun(runId: string | null) {
  const [view, dispatch] = useReducer(runReducer, initialRunView);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!runId) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(socketUrl(runId));
      socket.current = ws;
      ws.onopen = () => dispatch({ type: "connection", connected: true });
      ws.onmessage = (m) => dispatch(JSON.parse(m.data) as ServerMessage);
      ws.onclose = () => {
        dispatch({ type: "connection", connected: false });
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket.current?.close();
    };
  }, [runId]);

  const sendReview = (review: ReviewDecision) => socket.current?.send(JSON.stringify({ type: "review", review }));
  return { ...view, sendReview };
}
