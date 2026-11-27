/** Parsing a unified diff for display, tracking line numbers the same way the backend's parse_diff does. */

export interface DiffLine {
  kind: "add" | "del" | "ctx" | "hunk" | "meta";
  text: string;
  oldNo?: number;
  newNo?: number;
}

export interface DiffFile {
  path: string;
  status: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  lines: DiffLine[];
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

export function parseDiff(text: string): DiffFile[] {
  const files: DiffFile[] = [];
  let cur: DiffFile | null = null;
  let oldNo = 0;
  let newNo = 0;
  for (const raw of text.split("\n")) {
    if (raw.startsWith("diff --git ")) {
      const m = /^diff --git a\/(.+?) b\/(.+)$/.exec(raw);
      cur = { path: m ? m[2] : raw.split(" ").pop()!, status: "modified", additions: 0, deletions: 0, lines: [] };
      files.push(cur);
      continue;
    }
    if (!cur) continue;
    if (raw.startsWith("new file mode")) cur.status = "added";
    else if (raw.startsWith("deleted file mode")) cur.status = "deleted";
    else if (raw.startsWith("rename to ")) {
      cur.status = "renamed";
      cur.path = raw.slice("rename to ".length);
    } else if (raw.startsWith("+++ ") || raw.startsWith("--- ") || raw.startsWith("index ") || raw.startsWith("similarity ") || raw.startsWith("rename from ")) {
      continue;
    } else if (HUNK.test(raw)) {
      const m = HUNK.exec(raw)!;
      oldNo = Number(m[1]);
      newNo = Number(m[2]);
      cur.lines.push({ kind: "hunk", text: raw });
    } else if (raw.startsWith("+")) {
      cur.additions++;
      cur.lines.push({ kind: "add", text: raw.slice(1), newNo: newNo++ });
    } else if (raw.startsWith("-")) {
      cur.deletions++;
      cur.lines.push({ kind: "del", text: raw.slice(1), oldNo: oldNo++ });
    } else if (raw.startsWith(" ")) {
      cur.lines.push({ kind: "ctx", text: raw.slice(1), oldNo: oldNo++, newNo: newNo++ });
    } else if (raw.startsWith("\\")) {
      cur.lines.push({ kind: "meta", text: raw });
    }
  }
  return files;
}
