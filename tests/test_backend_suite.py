"""Orchestrate the backend pytest suite as a subprocess.

Marked `backend` + `slow` so it is excluded from the default smoke run.
Enable explicitly with::

    pytest -m backend            # only this orchestrator
    pytest -m "smoke or specs or backend"
    make test-all                # everything

We delegate to the backend's own pytest config (backend/pyproject.toml)
rather than re-discovering its tests from the root, which keeps coverage
thresholds and asyncio-mode settings owned by the backend.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tests.conftest import run_subprocess

pytestmark = [pytest.mark.backend, pytest.mark.slow]


def _resolve_pytest(backend_dir: Path) -> list[str] | None:
    """Pick the best pytest invocation available, preferring a venv."""
    for venv in (backend_dir / ".venv", Path(sys.prefix)):
        candidate = venv / "bin" / "pytest"
        if candidate.is_file():
            return [str(candidate)]
    if shutil.which("pytest"):
        return ["pytest"]
    # Last resort: invoke the current interpreter as a runner.
    return [sys.executable, "-m", "pytest"]


def test_backend_pytest_suite(backend_dir: Path) -> None:
    cmd = _resolve_pytest(backend_dir)
    if cmd is None:  # pragma: no cover - defensive
        pytest.skip("no pytest runner available")

    # `-q` keeps the nested output compact; backend's own pyproject sets
    # coverage thresholds + markers.
    result = run_subprocess([*cmd, "-q", "--tb=short"], cwd=backend_dir, timeout=900)
    if result.returncode != 0:
        pytest.fail(
            "backend pytest suite failed\n"
            f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
        )
