import pytest

from sdlc_orchestrator.demo import make_demo_repo


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))


@pytest.fixture
def demo_repo(tmp_path):
    return make_demo_repo(tmp_path / "repo")
