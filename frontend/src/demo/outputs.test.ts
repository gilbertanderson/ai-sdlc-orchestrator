import { prepareOutputs, pythonJsonDumps } from "./outputs";
import { reviewOf, type Golden, type Recording } from "./types";

const goldens = import.meta.glob<Golden>("./golden/*.json", { eager: true, import: "default" });
const recordings = import.meta.glob<Recording>("../../public/runs/*.json", { eager: true, import: "default" });

const recordingFor = (id: string) => {
  const r = Object.values(recordings).find((rec) => rec.id === id);
  if (!r) throw new Error(`no recording for golden ${id}`);
  return r;
};

describe("prepareOutputs matches Python's prepare_outputs", () => {
  const cases = Object.values(goldens).flatMap((g) => g.cases.map((c) => [g.id, c.name, c] as const));

  it("has golden cases for every recording", () => {
    expect(cases.length).toBeGreaterThanOrEqual(8);
    const recorded = Object.values(recordings).filter((r) => "messages" in r).map((r) => r.id).sort();
    expect(Object.values(goldens).map((g) => g.id).sort()).toEqual(recorded);
  });

  it.each(cases)("%s: %s", (id, _name, c) => {
    const rec = recordingFor(id);
    const review = reviewOf(rec);
    const out = prepareOutputs(rec.base_summary, review.findings, review.tests, c.review);
    // byte for byte, including the Markdown, the test files and the JSON report
    expect(Object.keys(out.files)).toEqual(Object.keys(c.expected.files));
    for (const [path, text] of Object.entries(c.expected.files)) expect(out.files[path]).toBe(text);
    expect(out).toEqual(c.expected);
  });
});

describe("pythonJsonDumps", () => {
  it("escapes like json.dumps(indent=2) with ensure_ascii", () => {
    const value = { a: "café ✓ 😀\u007f", b: [1, true, null, '\n\t"\\'], c: {}, d: [] };
    // printed by Python: json.dumps(value, indent=2)
    const python =
      '{\n  "a": "caf\\u00e9 \\u2713 \\ud83d\\ude00\\u007f",\n  "b": [\n    1,\n    true,\n    null,\n    "\\n\\t\\"\\\\"\n  ],\n  "c": {},\n  "d": []\n}';
    expect(pythonJsonDumps(value)).toBe(python);
  });
});
