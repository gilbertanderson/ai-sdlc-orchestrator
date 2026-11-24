export type Agent = "planner" | "summarizer" | "tests" | "security" | "orchestrator";
export type Phase = "plan" | "observe" | "execute" | "done" | "review" | "error";
export type RunStatus = "running" | "awaiting_review" | "done" | "error";

export interface AgentEvent {
  type: "event";
  agent: Agent;
  phase: Phase;
  message: string;
  data: Record<string, unknown>;
  ts: number;
}

export interface Summary {
  title: string;
  summary: string;
  changes?: string[];
  risk?: "low" | "medium" | "high";
  risk_reasons?: string[];
  testing_notes?: string[];
  reviewer_checklist?: string[];
  reasoning?: string;
}

export interface Finding {
  id: string;
  rule: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  cwe: string;
  file: string;
  line: number;
  snippet: string;
  fix: string;
  source: "rule" | "llm";
  explanation: string;
  dismissed: boolean;
}

export interface TestJob {
  file: string;
  test_path: string;
  status: "pending" | "written" | "failing" | "passing" | "gave_up";
  attempts: number;
  code: string;
  counts?: Record<string, number>;
  suspected_bugs?: string[];
  reasoning?: string;
}

export interface ReviewPayload {
  summary: Summary | null;
  findings: Finding[];
  tests: TestJob[];
}

export interface Report {
  status: "approved" | "rejected";
  output_dir: string;
  files: string[];
  applied_to_repo: boolean;
  summary: Summary;
  open_findings: number;
  tests_passing: number;
}

export interface RunSnapshot {
  id: string;
  request: { repo?: string | null; base: string; head: string; demo?: boolean };
  status: RunStatus;
  created: number;
  events: AgentEvent[];
  review: ReviewPayload | null;
  report: Report | null;
  error: string | null;
}

export interface ReviewDecision {
  decision: "approve" | "reject";
  title?: string;
  note: string;
  dismissed: string[];
  include_tests: boolean;
  apply_tests: boolean;
}

export type ServerMessage =
  | { type: "snapshot"; run: RunSnapshot }
  | AgentEvent
  | { type: "status"; status: RunStatus; review: ReviewPayload | null; report: Report | null; error: string | null }
  | { type: "error"; message: string };
