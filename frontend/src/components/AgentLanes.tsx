import type { AgentEvent, RunSnapshot } from "../types";

const LANES = [
  { agent: "planner", label: "Planner", blurb: "Reads the diff and picks agents", planKey: null },
  { agent: "summarizer", label: "PR summary", blurb: "Title, description, risk", planKey: "summarize" },
  { agent: "tests", label: "Test generation", blurb: "Write, run, read failures, retry", planKey: "tests" },
  { agent: "security", label: "Security scan", blurb: "Rules, then model review", planKey: "security" },
] as const;

type LaneState = "idle" | "working" | "done" | "skipped";

function laneState(events: AgentEvent[], planned: string[] | null, planKey: string | null, runActive: boolean): LaneState {
  if (planKey && planned && !planned.includes(planKey)) return "skipped";
  if (events.some((e) => e.phase === "done") || (planKey === null && planned)) return "done";
  if (events.length === 0) return runActive ? "idle" : "skipped";
  return runActive ? "working" : "done";
}

export function AgentLanes({ run }: { run: RunSnapshot }) {
  const planEvent = run.events.find((e) => e.agent === "planner" && e.phase === "plan" && Array.isArray(e.data.agents));
  const planned = (planEvent?.data.agents as string[] | undefined) ?? null;
  const active = run.status === "running";

  return (
    <div className="lanes">
      {LANES.map((lane) => {
        const events = run.events.filter((e) => e.agent === lane.agent);
        const state = laneState(events, planned, lane.planKey, active);
        return (
          <section key={lane.agent} className={`lane lane--${state}`} aria-label={lane.label}>
            <header className="lane__head">
              <span className={`dot dot--${state}`} aria-hidden />
              <div>
                <h3>{lane.label}</h3>
                <p>{lane.blurb}</p>
              </div>
              <span className="lane__state">{state}</span>
            </header>
            <ol className="lane__events">
              {events.map((e, i) => (
                <EventItem key={i} e={e} />
              ))}
              {state === "skipped" && <li className="muted">Not needed for this diff</li>}
            </ol>
          </section>
        );
      })}
    </div>
  );
}

function EventItem({ e }: { e: AgentEvent }) {
  const code = typeof e.data.code === "string" ? e.data.code : null;
  const output = typeof e.data.output === "string" ? e.data.output : null;
  return (
    <li className="event">
      <span className={`phase phase--${e.phase}`}>{e.phase}</span>
      <span className="event__msg">{e.message}</span>
      {code && (
        <details>
          <summary>Test code</summary>
          <pre>{code}</pre>
        </details>
      )}
      {output && (
        <details>
          <summary>pytest output</summary>
          <pre>{output}</pre>
        </details>
      )}
    </li>
  );
}
