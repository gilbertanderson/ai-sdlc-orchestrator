"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # "offline" runs a deterministic, rule-based model so the whole pipeline works
    # without cloud credentials. "bedrock" calls AWS Bedrock through the Converse API.
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "offline"))
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
    )
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    max_test_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_TEST_ATTEMPTS", "3")))
    max_test_files: int = field(default_factory=lambda: int(os.getenv("MAX_TEST_FILES", "3")))
    test_timeout_s: int = field(default_factory=lambda: int(os.getenv("TEST_TIMEOUT_S", "60")))
    runs_dir: Path = field(default_factory=lambda: Path(os.getenv("RUNS_DIR", "runs")).resolve())


def get_settings() -> Settings:
    return Settings()
