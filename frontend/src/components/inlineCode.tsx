import type { ReactNode } from "react";

/** Renders `backtick` spans as code, the way the agents write file and function names. */
export function withCode(text: string): ReactNode[] {
  return text.split("`").map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : part));
}
