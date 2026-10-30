"""Run the fleet's spec gate as first-class tests (marker ``specs``).

The gates are the hub's — bamr87/bamr87 ``templates/spec-driven/tools/``
(``spec_validator.py`` and ``backlog_lint.py``), consumed by reference. The
resolver ``tools/fleet-kit.sh`` finds them in the parent hub checkout when this
repo is checked out as the hub's submodule, else in a cached sparse clone under
``.fleet/`` (gitignored). CI runs the same gate through the hub's reusable
``spec-gate.yml``; ``make lint-specs`` runs it on a laptop.

Skips, rather than fails, when the kit cannot be resolved (offline on a
standalone clone): the by-reference gate still runs in CI, and a red test
that only says "no network" would teach people to ignore the tier.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.conftest import run_subprocess

pytestmark = pytest.mark.specs


@pytest.fixture(scope="module")
def kit_dir(repo_root: Path) -> Path:
    result = run_subprocess(["bash", "tools/fleet-kit.sh"], cwd=repo_root, timeout=180)
    if result.returncode != 0:
        pytest.skip(f"spec-driven kit not resolvable here: {result.stderr.strip()[:200]}")
    kit = Path(result.stdout.strip())
    assert (kit / "tools" / "spec_validator.py").is_file(), kit
    return kit


def test_spec_validator_passes(repo_root: Path, kit_dir: Path) -> None:
    result = run_subprocess(
        [sys.executable, str(kit_dir / "tools" / "spec_validator.py"), "--root", str(repo_root), "--strict"],
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        f"spec_validator failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_backlog_lint_passes(repo_root: Path, kit_dir: Path) -> None:
    result = run_subprocess(
        [sys.executable, str(kit_dir / "tools" / "backlog_lint.py"), "--root", str(repo_root)],
        cwd=repo_root,
    )
    assert result.returncode == 0, (
        f"backlog_lint failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_every_spec_dir_has_required_files(repo_root: Path) -> None:
    """Cheap structural pre-check that needs no kit at all."""
    specs = repo_root / "specs"
    spec_dirs = [p for p in specs.iterdir() if p.is_dir() and p.name[:3].isdigit()]
    assert spec_dirs, "no numbered spec directories found under specs/"
    missing = [
        f"{d.name}/{required}"
        for d in spec_dirs
        for required in ("spec.md", "plan.md", "tasks.md")
        if not (d / required).is_file()
    ]
    assert not missing, f"specs missing required files: {missing}"


def test_review_questions_declare_the_constitution_13_check(repo_root: Path) -> None:
    """The §13 review question used to be hard-coded in a local validator fork.

    It is data now: the kit's validator reads specs/_review_questions.json and
    warns (``--strict``: fails) when a spec that ranks or scores legal
    authority never answers "who is the stronger here?". Losing the file would
    silently drop the check.
    """
    import json

    data = json.loads((repo_root / "specs" / "_review_questions.json").read_text(encoding="utf-8"))
    markers = [q.get("answer_marker") for q in data.get("questions", [])]
    assert "who is the stronger" in markers, "specs/_review_questions.json must carry the constitution §13 question"
