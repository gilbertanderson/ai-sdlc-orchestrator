import { act, fireEvent, render, screen, within } from "@testing-library/react";

import DemoApp from "./DemoApp";
import { parseDiff } from "./diff";
import { Markdown } from "./Markdown";
import type { Recording, RecordingIndex } from "./types";

const files = import.meta.glob<Recording | RecordingIndex>("../../public/runs/*.json", { eager: true, import: "default" });
const byName = Object.fromEntries(Object.entries(files).map(([path, json]) => [path.split("/").pop()!, json]));

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const name = url.split("/").pop()!;
      return name in byName
        ? new Response(JSON.stringify(byName[name]), { status: 200 })
        : new Response("not found", { status: 404 });
    }),
  );
  URL.createObjectURL = vi.fn(() => "blob:demo");
  URL.revokeObjectURL = vi.fn();
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe("DemoApp", () => {
  it("replays a run, takes a review and offers the outputs", async () => {
    render(<DemoApp />);
    await flush();
    const index = byName["index.json"] as RecordingIndex;
    expect(screen.getAllByRole("button", { name: new RegExp(index.runs[0].title, "i") })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /^Watch a run/ }));
    await flush();
    expect(window.location.search).toBe(`?run=${index.runs[0].id}`);
    expect(screen.getByRole("heading", { level: 2, name: index.runs[0].title })).toBeInTheDocument();
    expect(screen.getByText("Agents working")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.getByRole("region", { name: "Planner" })).toHaveTextContent("Reading the diff");

    fireEvent.click(screen.getByRole("button", { name: "Skip to review" }));
    await flush();
    expect(screen.getByText("Needs your review")).toBeInTheDocument();
    const review = screen.getByRole("region", { name: "Human review" });
    expect(within(review).queryByText(/working tree/)).not.toBeInTheDocument();

    fireEvent.click(within(review).getByLabelText("Dismiss Hardcoded password or secret"));
    fireEvent.change(within(review).getByDisplayValue(/Add percentage and bulk discounts/), { target: { value: "Discounts and invoice export" } });
    fireEvent.click(within(review).getByRole("button", { name: "Approve" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    const result = screen.getByRole("region", { name: "Result" });
    expect(within(result).getByRole("heading", { name: "Approved" })).toHaveFocus();
    expect(within(result).getAllByRole("link", { name: /^Download/ })).toHaveLength(4);
    const pr = within(result).getByRole("region", { name: "PR description" });
    expect(within(pr).getByRole("heading", { name: "Discounts and invoice export" })).toBeInTheDocument();
    expect(within(pr).getByRole("table")).not.toHaveTextContent("Hardcoded password");
    expect(within(pr).getByText(/1 finding\(s\) reviewed and dismissed/)).toBeInTheDocument();

    fireEvent.click(within(pr).getByRole("button", { name: "Markdown" }));
    expect(within(pr).getByText(/^# Discounts and invoice export/)).toBeInTheDocument();
  });

  it("opens the run named in the address", async () => {
    window.history.replaceState(null, "", "/?run=clean");
    render(<DemoApp />);
    await flush();
    await flush();
    expect(screen.getByRole("heading", { level: 2, name: "A clean change" })).toBeInTheDocument();
  });

  it("shows an error when the recordings can't load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    render(<DemoApp />);
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load runs/index.json (500)");
  });
});

describe("parseDiff", () => {
  it("tracks file status and line numbers", () => {
    const files = parseDiff(
      "diff --git a/a.py b/a.py\nnew file mode 100644\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n" +
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -3,2 +3,2 @@ def f():\n     keep\n-old\n+new\n",
    );
    expect(files.map((f) => [f.path, f.status, f.additions, f.deletions])).toEqual([
      ["a.py", "added", 2, 0],
      ["b.py", "modified", 1, 1],
    ]);
    expect(files[1].lines.map((l) => [l.kind, l.newNo ?? null])).toEqual([
      ["hunk", null],
      ["ctx", 3],
      ["del", null],
      ["add", 4],
    ]);
  });
});

describe("Markdown", () => {
  it("renders the PR description subset and escapes text", () => {
    render(
      <Markdown
        text={"# Title <b>\n\n## Security review\n| Severity | Fix |\n|---|---|\n| high | use `x` |\n\n- one\n  - nested\n\n## Reviewer checklist\n- [ ] Check it\n\n_note_\n"}
      />,
    );
    expect(screen.getByRole("heading", { name: "Title <b>" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "use x" })).toBeInTheDocument();
    expect(screen.getByText("nested")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { hidden: true })).toBeDisabled();
    expect(screen.getByText("note").tagName).toBe("EM");
  });
});
