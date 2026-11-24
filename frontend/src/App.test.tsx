import { fireEvent, render, screen } from "@testing-library/react";

import { AgentLanes } from "./components/AgentLanes";
import { ReviewPanel } from "./components/ReviewPanel";
import { initialRunView, runReducer } from "./runReducer";
import type { AgentEvent, ReviewPayload, RunSnapshot } from "./types";

const ev = (agent: AgentEvent["agent"], phase: AgentEvent["phase"], message: string, data = {}): AgentEvent => ({
  type: "event",
  agent,
  phase,
  message,
  data,
  ts: 0,
});

const snapshot: RunSnapshot = {
  id: "abc",
  request: { repo: "/r", base: "main", head: "feat" },
  status: "running",
  created: 0,
  events: [],
  review: null,
  report: null,
  error: null,
};

const payload: ReviewPayload = {
  summary: { title: "Add discounts", summary: "Adds things.", risk: "medium", risk_reasons: ["No tests"], changes: ["Add x"] },
  findings: [
    { id: "f1", rule: "SEC004", title: "Shell injection", severity: "high", cwe: "CWE-78", file: "a.py", line: 3, snippet: "x", fix: "y", source: "rule", explanation: "", dismissed: false },
  ],
  tests: [{ file: "a.py", test_path: "tests/generated/test_a.py", status: "passing", attempts: 2, code: "def test(): pass", counts: { passed: 3 }, suspected_bugs: ["test_b"] }],
};

describe("runReducer", () => {
  it("applies snapshot, events and status updates in order", () => {
    let s = runReducer(initialRunView, ev("planner", "plan", "ignored before snapshot"));
    expect(s.run).toBeNull();
    s = runReducer(s, { type: "snapshot", run: snapshot });
    s = runReducer(s, ev("planner", "plan", "go"));
    s = runReducer(s, { type: "status", status: "awaiting_review", review: payload, report: null, error: null });
    expect(s.run?.events).toHaveLength(1);
    expect(s.run?.status).toBe("awaiting_review");
    expect(s.run?.review?.summary?.title).toBe("Add discounts");
  });
});

describe("AgentLanes", () => {
  it("marks agents the planner skipped", () => {
    const run = { ...snapshot, events: [ev("planner", "plan", "Running summarize", { agents: ["summarize"] })] };
    render(<AgentLanes run={run} />);
    expect(screen.getAllByText("Not needed for this diff")).toHaveLength(2);
    expect(screen.getByRole("region", { name: "PR summary" })).toHaveTextContent("idle");
  });
});

describe("ReviewPanel", () => {
  it("sends the edited title, dismissed findings and test choices", () => {
    const onSubmit = vi.fn();
    render(<ReviewPanel payload={payload} onSubmit={onSubmit} />);
    expect(screen.getByText(/Suspected bug in the code: test_b/)).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("Add discounts"), { target: { value: "Add bulk discounts" } });
    fireEvent.click(screen.getByLabelText("Dismiss Shell injection"));
    fireEvent.click(screen.getByLabelText(/write them into the repository/));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onSubmit).toHaveBeenCalledWith({
      decision: "approve",
      title: "Add bulk discounts",
      note: "",
      dismissed: ["f1"],
      include_tests: true,
      apply_tests: true,
    });
  });
});
