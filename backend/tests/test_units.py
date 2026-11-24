import pytest

from sdlc_orchestrator.diff import git_diff, parse_diff
from sdlc_orchestrator.llm import OfflineLLM, _doc_examples, extract_json
from sdlc_orchestrator.security_rules import scan
from sdlc_orchestrator.testrunner import changed_functions, module_path

DIFF = """diff --git a/app/auth.py b/app/auth.py
new file mode 100644
--- /dev/null
+++ b/app/auth.py
@@ -0,0 +1,4 @@
+import os
+DB_PASSWORD = "hunter22secret"
+def run(cmd):
+    os.system(cmd)
diff --git a/web/view.tsx b/web/view.tsx
--- a/web/view.tsx
+++ b/web/view.tsx
@@ -10,2 +10,3 @@ export function View() {
   const a = 1;
-  return <div>{a}</div>;
+  // dangerouslySetInnerHTML is fine in a comment
+  return <div dangerouslySetInnerHTML={{ __html: a }} />;
"""


def test_parse_diff_tracks_status_and_line_numbers():
    files = parse_diff(DIFF)
    assert [f.path for f in files] == ["app/auth.py", "web/view.tsx"]
    auth, view = files
    assert auth.status == "added" and auth.language == "python" and auth.additions == 4
    assert [a.line for a in auth.added_lines] == [1, 2, 3, 4]
    assert view.status == "modified" and view.deletions == 1
    assert [a.line for a in view.added_lines] == [11, 12]


def test_scan_finds_rule_hits_and_skips_comments():
    hits = scan(parse_diff(DIFF))
    by_rule = {h.rule: h for h in hits}
    assert set(by_rule) == {"SEC003", "SEC005", "SEC011"}
    assert by_rule["SEC003"].line == 2 and by_rule["SEC003"].severity == "high"
    assert by_rule["SEC011"].line == 12  # the comment on line 11 is ignored
    assert hits[0].severity == "high"  # sorted by severity


def test_scan_respects_language_filters():
    diff = "diff --git a/x.go b/x.go\n--- a/x.go\n+++ b/x.go\n@@ -1 +1,2 @@\n x\n+os.system(cmd)\n"
    assert scan(parse_diff(diff)) == []


def test_git_diff_reads_branch(demo_repo):
    files = parse_diff(git_diff(demo_repo, "main", "feature/discounts"))
    assert {f.path for f in files} == {"invoices/pricing.py", "invoices/export.py"}


@pytest.mark.parametrize(
    "text",
    ['{"a": 1}', 'Sure!\n```json\n{"a": 1}\n```', 'prefix {"a": 1} suffix {"b": 2}', '{"a": 1, "s": "brace } inside"}'],
)
def test_extract_json(text):
    assert extract_json(text)["a"] == 1


def test_extract_json_rejects_prose():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_doc_examples_handles_values_and_exceptions():
    doc = """Thing.

    >>> f(1)
    2
    >>> f(-1)
    Traceback (most recent call last):
    ValueError: bad
    """
    ex = _doc_examples(doc)
    assert ex[0] == ("f(1)", "2")
    assert ex[1][0] == "f(-1)" and ex[1][1].endswith("ValueError: bad")


def test_module_path_and_changed_functions():
    assert module_path("src/pkg/mod.py") == "pkg.mod"
    assert module_path("pkg/__init__.py") == "pkg"
    src = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    change = parse_diff("diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -4,0 +5,2 @@\n+def b():\n+    return 2\n")[0]
    assert changed_functions(src, change) == ["b"]


def test_offline_planner_skips_tests_without_python_source():
    files = [f.to_dict() for f in parse_diff(DIFF)]
    files = [f for f in files if f["path"].endswith(".tsx")]
    plan = OfflineLLM().run("plan", "", "", {"files": files, "additions": 2, "deletions": 1, "commits": []})
    assert plan["agents"] == ["summarize", "security"]
    assert "tests" in plan["reasoning"]


def test_offline_security_dismisses_placeholders():
    cands = [{"id": "x", "rule": "SEC003", "snippet": 'token = "changeme123"', "file": "a.py", "severity": "high", "title": "t"}]
    out = OfflineLLM().run("security_review", "", "", {"candidates": cands})
    assert out["confirmed"] == [] and out["false_positives"][0]["id"] == "x"


def test_bedrock_llm_parses_reply_and_retries_bad_json(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    from types import SimpleNamespace

    from sdlc_orchestrator.config import Settings
    from sdlc_orchestrator.llm import BedrockLLM

    llm = BedrockLLM(Settings(llm_provider="bedrock"))
    replies = iter(["Here you go, no JSON", [{"type": "text", "text": '{"agents": ["summarize"], "reasoning": "r"}'}]])
    calls = []

    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=next(replies))

    llm._model = SimpleNamespace(invoke=invoke)
    out = llm.run("plan", "sys", "user", {})
    assert out["agents"] == ["summarize"]
    assert len(calls) == 2 and calls[1][-1][0] == "human"
    assert llm.name.startswith("bedrock:")
