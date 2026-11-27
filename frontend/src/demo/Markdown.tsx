import type { ReactNode } from "react";

import { withCode } from "../components/inlineCode";

/**
 * Renders the Markdown subset that render_pr_description produces: headings, lists
 * with one level of nesting, task lists, tables, italic lines and inline code.
 * Everything becomes React elements, so text from the model or the reviewer is
 * always escaped.
 */
export function Markdown({ text }: { text: string }) {
  return <div className="md">{blocks(text)}</div>;
}

const inline = withCode;

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());

function blocks(text: string): ReactNode[] {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = i;
    if (!line.trim()) {
      i++;
    } else if (line.startsWith("# ")) {
      out.push(<h4 key={key}>{inline(line.slice(2))}</h4>);
      i++;
    } else if (line.startsWith("## ")) {
      out.push(<h5 key={key}>{inline(line.slice(3))}</h5>);
      i++;
    } else if (line.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const [head, , ...body] = rows;
      out.push(
        <div className="md__table" key={key} tabIndex={0} role="group" aria-label="Table, scrolls sideways on small screens">
          <table>
            <thead>
              <tr>
                {cells(head).map((c, j) => (
                  <th key={j}>{inline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, k) => (
                <tr key={k}>
                  {cells(r).map((c, j) => (
                    <td key={j}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    } else if (line.startsWith("- ")) {
      const items: { text: string; children: string[] }[] = [];
      while (i < lines.length && (lines[i].startsWith("- ") || (lines[i].startsWith("  - ") && items.length))) {
        if (lines[i].startsWith("- ")) items.push({ text: lines[i].slice(2), children: [] });
        else items[items.length - 1].children.push(lines[i].slice(4));
        i++;
      }
      const tasks = items.every((it) => it.text.startsWith("[ ] "));
      out.push(
        <ul key={key} className={tasks ? "md__tasks" : undefined}>
          {items.map((it, j) => (
            <li key={j}>
              {tasks ? (
                <>
                  <input type="checkbox" disabled aria-hidden tabIndex={-1} /> {inline(it.text.slice(4))}
                </>
              ) : (
                inline(it.text)
              )}
              {it.children.length > 0 && (
                <ul>
                  {it.children.map((c, k) => (
                    <li key={k}>{inline(c)}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>,
      );
    } else if (/^_.+_$/.test(line.trim())) {
      out.push(
        <p key={key}>
          <em>{inline(line.trim().slice(1, -1))}</em>
        </p>,
      );
      i++;
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#|\||- |_.+_$)/.test(lines[i])) para.push(lines[i++]);
      if (para.length === 0) para.push(lines[i++]);
      out.push(<p key={key}>{inline(para.join(" "))}</p>);
    }
  }
  return out;
}
