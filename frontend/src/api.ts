import type { ReviewDecision, RunSnapshot } from "./types";

export interface RunListItem {
  id: string;
  status: RunSnapshot["status"];
  created: number;
  request: RunSnapshot["request"];
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => json<{ ok: boolean; version: string; model: string }>(r)),
  listRuns: () => fetch("/api/runs").then((r) => json<RunListItem[]>(r)),
  startRun: (body: { demo?: boolean; repo?: string; base?: string; head?: string }) =>
    fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(
      (r) => json<{ id: string }>(r),
    ),
  review: (id: string, decision: ReviewDecision) =>
    fetch(`/api/runs/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    }).then((r) => json<{ ok: boolean }>(r)),
};

export function socketUrl(id: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/runs/${id}`;
}
