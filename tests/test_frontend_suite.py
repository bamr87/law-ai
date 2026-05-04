"""Orchestrate the frontend vitest suite as a subprocess.

Marked `frontend` + `slow` so the default smoke run skips it. Requires
`npm` on PATH and `frontend/node_modules` populated (`npm install`).

Enable with::

    pytest -m frontend
    make test-frontend
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import run_subprocess

pytestmark = [pytest.mark.frontend, pytest.mark.slow]


def test_frontend_vitest_suite(frontend_dir: Path, have_npm: bool) -> None:
    if not have_npm:
        pytest.skip("npm not on PATH")
    if not (frontend_dir / "node_modules").is_dir():
        pytest.skip("frontend/node_modules missing — run `npm install` first")

    result = run_subprocess(
        ["npm", "test", "--", "--run"], cwd=frontend_dir, timeout=900
    )
    if result.returncode != 0:
        pytest.fail(
            "frontend vitest suite failed\n"
            f"--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
        )
