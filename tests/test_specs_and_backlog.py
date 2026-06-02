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


def test_status_vs_tasks_drift_check_fires(repo_root: Path, tmp_path: Path) -> None:
    """Synthetic spec with status='shipped' but unchecked tasks must fail."""
    sys.path.insert(0, str(repo_root))
    try:
        from scripts.spec_validator import validate_spec  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    spec_dir = tmp_path / "999-drift-fixture"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text(
        "# Spec: Drift Fixture\n\n"
        "- **ID**: 999-drift-fixture\n"
        "- **Status**: shipped\n\n"
        "## 6. Functional Requirements\n- **FR-1**: thing.\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## T-001 — do thing\n- **Refs**: FR-1\n- **Status**: `[ ]`\n\n"
        "## Follow-ups Discovered\n- _none_\n",
        encoding="utf-8",
    )
    errors = validate_spec(spec_dir)
    drift_errors = [e for e in errors if "status='shipped' but" in e]
    assert drift_errors, f"expected drift error, got: {errors}"

    # Flip the unchecked task to done; drift error must disappear.
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## T-001 — do thing\n- **Refs**: FR-1\n- **Status**: `[x]`\n\n"
        "## Follow-ups Discovered\n- _none_\n",
        encoding="utf-8",
    )
    errors_after = validate_spec(spec_dir)
    assert not [e for e in errors_after if "status='shipped' but" in e], errors_after


def test_status_vs_tasks_forgotten_bump_check_fires(
    repo_root: Path, tmp_path: Path
) -> None:
    """All tasks `[x]` but status still pre-shipped must fail (forgotten bump)."""
    sys.path.insert(0, str(repo_root))
    try:
        from scripts.spec_validator import validate_spec  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    spec_dir = tmp_path / "999-forgotten-bump"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text(
        "# Spec: Forgotten Bump\n\n"
        "- **ID**: 999-forgotten-bump\n"
        "- **Status**: in-progress\n\n"
        "## 6. Functional Requirements\n- **FR-1**: thing.\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## T-001 — do thing\n- **Refs**: FR-1\n- **Status**: `[x]`\n\n"
        "## Follow-ups Discovered\n- _none_\n",
        encoding="utf-8",
    )
    errors = validate_spec(spec_dir)
    bump_errors = [e for e in errors if "but status='in-progress'" in e]
    assert bump_errors, f"expected forgotten-bump error, got: {errors}"
