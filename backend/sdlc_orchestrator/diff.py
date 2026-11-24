"""Reading and parsing unified diffs."""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
    ".cs": "csharp",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".tf": "terraform",
    ".sh": "shell",
    ".sql": "sql",
}
CODE_LANGUAGES = {"python", "typescript", "javascript", "go", "java", "ruby", "rust", "csharp", "shell", "sql", "terraform"}

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class AddedLine:
    line: int
    text: str


@dataclass
class FileChange:
    path: str
    status: str = "modified"  # added | modified | deleted | renamed
    language: str = "other"
    additions: int = 0
    deletions: int = 0
    added_lines: list[AddedLine] = field(default_factory=list)
    patch: str = ""

    @property
    def is_code(self) -> bool:
        return self.language in CODE_LANGUAGES

    @property
    def is_test(self) -> bool:
        name = Path(self.path).name
        return (
            name.startswith("test_")
            or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.go"))
            or "/tests/" in f"/{self.path}"
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_code"] = self.is_code
        d["is_test"] = self.is_test
        return d


def language_for(path: str) -> str:
    return LANGUAGES.get(Path(path).suffix.lower(), "other")


def parse_diff(text: str) -> list[FileChange]:
    """Parse `git diff` output into per-file changes with added-line numbers."""
    files: list[FileChange] = []
    cur: FileChange | None = None
    new_line = 0
    patch_lines: list[str] = []

    def close() -> None:
        if cur is not None:
            cur.patch = "\n".join(patch_lines)
            files.append(cur)

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            close()
            patch_lines = [raw]
            m = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            path = m.group(2) if m else raw.split()[-1]
            cur = FileChange(path=path, language=language_for(path))
            continue
        if cur is None:
            continue
        patch_lines.append(raw)
        if raw.startswith("new file mode"):
            cur.status = "added"
        elif raw.startswith("deleted file mode"):
            cur.status = "deleted"
        elif raw.startswith("rename to "):
            cur.status = "renamed"
            cur.path = raw[len("rename to "):]
            cur.language = language_for(cur.path)
        elif raw.startswith("+++ ") or raw.startswith("--- "):
            continue
        elif m := _HUNK.match(raw):
            new_line = int(m.group(1))
        elif raw.startswith("+"):
            cur.additions += 1
            cur.added_lines.append(AddedLine(new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            cur.deletions += 1
        elif raw.startswith(" "):
            new_line += 1
    close()
    return files


def git_diff(repo: str | Path, base: str, head: str = "HEAD") -> str:
    """Return the diff of `head` against its merge base with `base`."""
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "--no-color", "-M", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def git_log(repo: str | Path, base: str, head: str = "HEAD") -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def read_at(repo: str | Path, ref: str, path: str) -> str | None:
    out = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
    )
    return out.stdout if out.returncode == 0 else None
