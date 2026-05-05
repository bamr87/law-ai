"""Shared fixtures for the repo-wide test suite.

The root `tests/` package is the single entry point for validating the
LawGraph AI monorepo end-to-end: structure, specs/backlog, docs, configs,
and (opt-in) backend + frontend test suites.

Per AGENTS.md, these tests must remain dependency-light so they can run in
any environment that has a Python 3.11+ interpreter and the repo checked
out — no Docker, no Neo4j, no node_modules required for the default
(smoke + specs) tier.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def backend_dir(repo_root: Path) -> Path:
    return repo_root / "backend"


@pytest.fixture(scope="session")
def frontend_dir(repo_root: Path) -> Path:
    return repo_root / "frontend"


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


@pytest.fixture(scope="session")
def have_npm() -> bool:
    return _which("npm") is not None


@pytest.fixture(scope="session")
def have_pytest() -> bool:
    return _which("pytest") is not None or _which("python") is not None


def run_subprocess(
    cmd: Iterable[str],
    cwd: Path,
    *,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and return the completed result.

    Captures stdout/stderr as text. Does NOT raise on non-zero exit so
    callers can attach the output to assertion messages.
    """
    return subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
