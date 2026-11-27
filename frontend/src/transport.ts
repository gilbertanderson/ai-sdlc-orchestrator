import { socketUrl } from "./api";
import type { ReviewDecision, ServerMessage } from "./types";

export interface RunHandlers {
  message: (m: ServerMessage) => void;
  connection: (connected: boolean) => void;
}

/**
 * Where a run's messages come from. The dashboard only ever sees `ServerMessage`s,
 * so the live server and the browser demo's recorded replays look the same to it.
 */
export interface RunSource {
  /** Starts delivering messages; returns a function that stops them. */
  connect(handlers: RunHandlers): () => void;
  sendReview(review: ReviewDecision): void;
}

/** A run on the local server, over WebSocket, reconnecting if the socket drops mid-run. */
export function serverSource(runId: string): RunSource {
  let socket: WebSocket | null = null;
  return {
    connect({ message, connection }) {
      let closed = false;
      let retry: ReturnType<typeof setTimeout> | undefined;
      const open = () => {
        const ws = new WebSocket(socketUrl(runId));
        socket = ws;
        ws.onopen = () => connection(true);
        ws.onmessage = (m) => message(JSON.parse(m.data) as ServerMessage);
        ws.onclose = () => {
          connection(false);
          if (!closed) retry = setTimeout(open, 1500);
        };
      };
      open();
      return () => {
        closed = true;
        clearTimeout(retry);
        socket?.close();
      };
    },
    sendReview(review) {
      socket?.send(JSON.stringify({ type: "review", review }));
    },
  };
}
