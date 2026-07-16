"""Repo structure invariants.

Acts as a fast guardrail: if any required top-level file or directory is
deleted or moved, this test fires before deeper tests can mislead.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "PRD.md",
    "BACKLOG.md",
    "Makefile",
    "docker-compose.yml",
    ".env.example",
    ".github/copilot-instructions.md",
    "backend/pyproject.toml",
    "backend/Dockerfile",
    "backend/manage.py",
    "backend/law_ai/asgi.py",
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/postcss.config.js",
    "scripts/spec_validator.py",
    "scripts/backlog_lint.py",
]

REQUIRED_DIRS = [
    "backend/law_ai/agents_runtime",
    "backend/law_ai/agentsapi",
    "backend/law_ai/analysis",
    "backend/law_ai/audit",
    "backend/law_ai/core",
    "backend/law_ai/graph",
    "backend/law_ai/ingestionapp",
    "backend/law_ai/lsat",
    "backend/law_ai/settings",
    "backend/tests",
    "frontend/app",
    "frontend/components",
    "frontend/lib",
    "frontend/__tests__",
    "docs",
    "prompts",
    "scripts",
    "specs",
    "tests",
]


@pytest.mark.parametrize("relpath", REQUIRED_FILES)
def test_required_file_exists(repo_root: Path, relpath: str) -> None:
    path = repo_root / relpath
    assert path.is_file(), f"missing required file: {relpath}"


@pytest.mark.parametrize("relpath", REQUIRED_DIRS)
def test_required_dir_exists(repo_root: Path, relpath: str) -> None:
    path = repo_root / relpath
    assert path.is_dir(), f"missing required directory: {relpath}"


def test_no_forbidden_ai_agent_configs(repo_root: Path) -> None:
    """AGENTS.md forbids non-Copilot agent configs in the repo."""
    forbidden = [
        ".cursorrules",
        ".cursor",
        ".continuerc.json",
        ".continue",
        ".aider.conf.yml",
        ".aiderignore",
        ".codeium",
        ".windsurfrules",
    ]
    found = [name for name in forbidden if (repo_root / name).exists()]
    assert not found, (
        f"forbidden AI agent config(s) present (see AGENTS.md § Development "
        f"Orchestration): {found}"
    )
