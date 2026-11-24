"""Running generated tests against a clean checkout of the PR head."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .diff import FileChange


def module_path(path: str) -> str:
    p = Path(path).with_suffix("")
    parts = list(p.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def changed_functions(source: str, change: FileChange) -> list[str]:
    """Top-level functions whose body overlaps an added line."""
    added = {a.line for a in change.added_lines}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            if any(start <= n <= (node.end_lineno or node.lineno) for n in added):
                names.append(node.name)
    return names


def symbols(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


class Checkout:
    """A throwaway copy of the repository at a given ref."""

    def __init__(self, repo: str | Path, ref: str):
        self.dir = Path(tempfile.mkdtemp(prefix="sdlc-orch-"))
        archive = self.dir / "src.tar"
        subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "-o", str(archive), ref], check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(self.dir, filter="data")
        archive.unlink()

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


@dataclass
class TestRun:
    passed: bool
    exit_code: int
    output: str
    counts: dict[str, int]


def run_pytest(checkout: Checkout, test_rel_path: str, code: str, timeout: int) -> TestRun:
    target = checkout.dir / test_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code)
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(checkout.dir), str(checkout.dir / "src")]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", test_rel_path],
            cwd=checkout.dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output, code_ = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        output, code_ = f"pytest timed out after {timeout}s\n{e.stdout or ''}", 124
    counts = {}
    for word in ("passed", "failed", "error", "xfailed", "xpassed", "skipped"):
        m = re.search(rf"(\d+) {word}", output)
        if m:
            counts[word] = int(m.group(1))
    # exit code 5 means no tests were collected
    return TestRun(passed=code_ == 0, exit_code=code_, output=output[-6000:], counts=counts)
