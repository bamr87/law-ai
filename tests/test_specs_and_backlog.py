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
        from scripts.spec_validator import (
            validate_spec,  # type: ignore[import-not-found]
        )
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
        from scripts.spec_validator import (
            validate_spec,  # type: ignore[import-not-found]
        )
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


def test_superseded_is_a_completed_status(repo_root: Path, tmp_path: Path) -> None:
    """A retired spec may say so in the field the validator reads.

    `superseded` means "this shipped and a later spec replaced it". Before
    BL-20260906-47 the only completed status was `shipped`, so the symmetric
    check ("every task `[x]` but status is not shipped") rejected the word and
    specs/025-lsat-static-site had to hide it in prose after the status.
    """
    sys.path.insert(0, str(repo_root))
    try:
        from scripts.spec_validator import (
            validate_spec,  # type: ignore[import-not-found]
        )
    finally:
        sys.path.pop(0)

    spec_dir = tmp_path / "999-superseded"
    spec_dir.mkdir()
    (spec_dir / "spec.md").write_text(
        "# Spec: Superseded Fixture\n\n"
        "- **ID**: 999-superseded\n"
        "- **Status**: superseded\n\n"
        "## 6. Functional Requirements\n- **FR-1**: thing.\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    done = (
        "# Tasks\n\n"
        "## T-001 — do thing\n- **Refs**: FR-1\n- **Status**: `[x]`\n\n"
        "## Follow-ups Discovered\n- _none_\n"
    )
    (spec_dir / "tasks.md").write_text(done, encoding="utf-8")
    assert not [e for e in validate_spec(spec_dir) if "status=" in e], (
        "a superseded spec with every task done must pass"
    )

    # ...and it carries the same obligation `shipped` does: the work really is
    # finished, so an unchecked task is still an error.
    (spec_dir / "tasks.md").write_text(done.replace("`[x]`", "`[ ]`"), "utf-8")
    assert [e for e in validate_spec(spec_dir) if "status='superseded' but" in e]


# ---------------------------------------------------------------------------
# Stale-backlog reporter (BL-20260503-14). Feeds the nightly triage issue in
# .github/workflows/nightly-tests.yml.
# ---------------------------------------------------------------------------


def _backlog_lint_module(repo_root: Path):
    """Import scripts/backlog_lint.py by path (scripts/ is not a package)."""
    import importlib.util

    path = repo_root / "scripts" / "backlog_lint.py"
    spec = importlib.util.spec_from_file_location("_backlog_lint_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SAMPLE_BACKLOG = """# Backlog

## Open

- **BL-20250101-01** — *infra, low* — Ancient open item.
- **BL-20260901-02** — *infra, low* — Fresh open item.

## Claimed

- **BL-20250101-03** — *infra, low* — Ancient but claimed. claimed-by:specs/001-x

## Done

- **BL-20250101-04** — *infra, low* — Ancient but done.
"""


def test_stale_report_flags_only_old_open_items(repo_root: Path) -> None:
    import datetime as dt

    mod = _backlog_lint_module(repo_root)
    stale = mod.stale_open_items(
        _SAMPLE_BACKLOG, days=60, today=dt.date(2026, 9, 5)
    )
    ids = [row[1] for row in stale]
    assert ids == ["BL-20250101-01"], (
        f"only ## Open items past the cutoff are triage material; got {ids}"
    )
    assert stale[0][0] > 60, "age in days should be reported"


def test_stale_report_cli_never_fails(repo_root: Path) -> None:
    """The nightly step must never redden a run: exit 0 in both branches."""
    for days in ("0", "100000"):
        result = run_subprocess(
            [sys.executable, "scripts/backlog_lint.py", "--stale-report",
             "--stale-days", days],
            cwd=repo_root,
        )
        assert result.returncode == 0, (
            f"--stale-report --stale-days {days} exited "
            f"{result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
    # The "nothing stale" sentinel the workflow greps for must be stable.
    quiet = run_subprocess(
        [sys.executable, "scripts/backlog_lint.py", "--stale-report",
         "--stale-days", "100000"],
        cwd=repo_root,
    )
    assert quiet.stdout.startswith("No ## Open items older than")


def test_nightly_workflow_wires_the_stale_reporter(repo_root: Path) -> None:
    """The reporter is only useful if the scheduled workflow calls it."""
    wf = (repo_root / ".github" / "workflows" / "nightly-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "--stale-report" in wf, "nightly run must invoke the stale reporter"
    assert "gh issue create" in wf, "stale items must open a triage issue"
    assert "issues: write" in wf, "opening an issue needs the issues permission"


def test_spec_template_and_specify_prompt_carry_the_s13_review_question(
    repo_root: Path,
) -> None:
    """BL-20260803-05: §13's review question must be asked at the spec gate.

    docs/constitution.md §13 requires "who is the stronger here, and what does
    this feature do for them?" to be answered in spec §2 for any feature that
    ranks, scores or summarizes legal authority. That only happens by default
    if the template a spec is copied from and the /specify prompt both say so.
    """
    template = (repo_root / "specs" / "_template" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert "## 2. Origin & Background" in template, (
        "the template must carry §2 Origin & Background — /specify tells "
        "writers to record claimed backlog IDs there"
    )
    assert "who is the stronger here" in template.lower()
    assert "§13" in template

    prompt = (repo_root / "prompts" / "specify.md").read_text(encoding="utf-8")
    assert "who is the stronger here" in prompt.lower()
    assert "§§1–13" in prompt, "/specify must confirm §§1–13, not only §§1–11"


def test_s13_review_question_warning_fires_on_a_ranking_spec(
    repo_root: Path, tmp_path: Path
) -> None:
    """The validator warns (never fails) when a live spec skips the question."""
    sys.path.insert(0, str(repo_root / "scripts"))
    try:
        import spec_validator
    finally:
        sys.path.pop(0)

    spec_dir = tmp_path / "900-rank-authorities"
    spec_dir.mkdir()
    header = (
        "# Spec: Ranker\n\n- **ID**: 900-rank-authorities\n"
        "- **Status**: {status}\n\n## 2. Origin & Background\n\n{body}\n"
    )
    ranking_line = (
        "- **FR-1**: rank each precedent by citation count over the authority "
        "graph.\n"
    )

    (spec_dir / "spec.md").write_text(
        header.format(status="in-progress", body=ranking_line), encoding="utf-8"
    )
    warnings = spec_validator.stronger_question_warnings(spec_dir)
    assert warnings, "a live ranking spec with no §13 answer must warn"
    assert "who is the stronger" in warnings[0]

    # Answering the question silences it.
    (spec_dir / "spec.md").write_text(
        header.format(
            status="in-progress",
            body=ranking_line
            + (
                "- Who is the stronger here? Repeat players, and the score "
                "is labelled as citation volume, never correctness.\n"
            ),
        ),
        encoding="utf-8",
    )
    assert not spec_validator.stronger_question_warnings(spec_dir)

    # Unrelated scoring next to no authority language must stay quiet.
    (spec_dir / "spec.md").write_text(
        header.format(
            status="in-progress",
            body="- **FR-1**: score the learner's practice drill.\n",
        ),
        encoding="utf-8",
    )
    assert not spec_validator.stronger_question_warnings(spec_dir)


def _strict_fixture(spec_dir: Path, *, answered: bool) -> None:
    """A minimal spec package that is valid but trips the §13 warning."""
    spec_dir.mkdir(parents=True, exist_ok=True)
    answer = (
        "- Who is the stronger here? Repeat players; the score is labelled "
        "as citation volume, never correctness.\n"
        if answered
        else ""
    )
    (spec_dir / "spec.md").write_text(
        "# Spec: Strict Fixture\n\n"
        "- **ID**: 900-strict-fixture\n"
        "- **Status**: in-progress\n\n"
        "## 2. Origin & Background\n\n"
        f"{answer}\n"
        "## 6. Functional Requirements\n"
        "- **FR-1**: rank each precedent by citation count over the "
        "authority graph.\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## T-001 — do thing\n- **Refs**: FR-1\n- **Status**: `[ ]`\n\n"
        "## Follow-ups Discovered\n- _none_\n",
        encoding="utf-8",
    )


def test_strict_turns_the_s13_warning_into_a_failure(
    repo_root: Path, tmp_path: Path
) -> None:
    """BL-20260906-48: --strict is what makes the WARN lines reach anyone."""
    spec_dir = tmp_path / "900-strict-fixture"
    _strict_fixture(spec_dir, answered=False)

    advisory = run_subprocess(
        [sys.executable, "scripts/spec_validator.py", str(spec_dir)], cwd=repo_root
    )
    assert advisory.returncode == 0, advisory.stdout
    assert "WARN " in advisory.stdout

    strict = run_subprocess(
        [sys.executable, "scripts/spec_validator.py", "--strict", str(spec_dir)],
        cwd=repo_root,
    )
    assert strict.returncode == 1, strict.stdout
    assert "WARN " in strict.stdout
    assert "--strict" in strict.stdout

    # Answering the question clears the gate; --strict is not a blanket veto.
    _strict_fixture(spec_dir, answered=True)
    answered = run_subprocess(
        [sys.executable, "scripts/spec_validator.py", "--strict", str(spec_dir)],
        cwd=repo_root,
    )
    assert answered.returncode == 0, answered.stdout
    assert "WARN " not in answered.stdout


def test_the_spec_gate_actually_passes_strict(repo_root: Path) -> None:
    """A flag no gate passes is a flag that changes nothing."""
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    assert "scripts/spec_validator.py --strict" in makefile, (
        "make lint-specs must run the validator with --strict"
    )
    ci = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/spec_validator.py --strict" in ci, (
        "the CI spec gate must run the validator with --strict"
    )
