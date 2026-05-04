"""Run the spec + backlog linters as first-class tests.

These wrap the canonical scripts in scripts/ so a single `pytest` at the
repo root surfaces spec-drift and backlog-format failures without having
to remember the standalone commands.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.conftest import run_subprocess

pytestmark = pytest.mark.specs


def test_spec_validator_passes(repo_root: Path) -> None:
    result = run_subprocess(
        [sys.executable, "scripts/spec_validator.py"], cwd=repo_root
    )
    assert result.returncode == 0, (
        f"spec_validator failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_backlog_lint_passes(repo_root: Path) -> None:
    result = run_subprocess(
        [sys.executable, "scripts/backlog_lint.py"], cwd=repo_root
    )
    assert result.returncode == 0, (
        f"backlog_lint failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_every_spec_dir_has_required_files(repo_root: Path) -> None:
    """Cheap structural pre-check before invoking the full validator."""
    specs = repo_root / "specs"
    spec_dirs = [
        p
        for p in specs.iterdir()
        if p.is_dir() and p.name[:3].isdigit()
    ]
    assert spec_dirs, "no numbered spec directories found under specs/"
    missing: list[str] = []
    for d in spec_dirs:
        for required in ("spec.md", "plan.md", "tasks.md"):
            if not (d / required).is_file():
                missing.append(f"{d.name}/{required}")
    assert not missing, f"specs missing required files: {missing}"
