"""Unit tests for scripts/visual_evidence_gate.py — BL-20260905-05.

The gate is the mechanical half of the visual-evidence convention: a PR that
changes `frontend/` or `lsat-static/` must attach a screenshot or commit one
under `docs/images/`. These tests pin the decision table, because the two ways
this gate could be wrong are both expensive: too strict and every bot PR and
refactor is blocked, too loose and it silently passes everything.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def gate(repo_root: Path) -> ModuleType:
    """Import the script by path — scripts/ is not an importable package."""
    path = repo_root / "scripts" / "visual_evidence_gate.py"
    spec = importlib.util.spec_from_file_location("_visual_evidence_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the gate does not apply -------------------------------------------------


def test_backend_only_change_is_out_of_scope(gate: ModuleType) -> None:
    ok, message = gate.evaluate("", ["backend/law_ai/core/llm/router.py"])
    assert ok
    assert "does not apply" in message


def test_docs_only_change_is_out_of_scope(gate: ModuleType) -> None:
    ok, _ = gate.evaluate("", ["docs/architecture.md", "AGENTS.md"])
    assert ok


# --- the gate applies and fails ----------------------------------------------


def test_lockfile_only_change_is_out_of_scope(gate: ModuleType) -> None:
    ok, message = gate.evaluate(
        "", ["frontend/package-lock.json", "lsat-static/package-lock.json"]
    )
    assert ok
    assert "does not apply" in message


def test_manifest_bump_with_a_lockfile_is_still_gated(gate: ModuleType) -> None:
    ok, message = gate.evaluate(
        "", ["frontend/package.json", "frontend/package-lock.json"]
    )
    assert not ok
    assert "frontend/package.json" in message
    assert "package-lock.json" not in message


def test_frontend_change_without_evidence_fails(gate: ModuleType) -> None:
    ok, message = gate.evaluate(
        "Refactored the shell.", ["frontend/components/shell/AppShell.tsx"]
    )
    assert not ok
    assert "no visual evidence" in message
    assert "no-visual-change" in message, "the failure must name the opt-out"
    assert "docs/ui-ux-review.md" in message, "and point at the docs"


def test_lsat_static_change_without_evidence_fails(gate: ModuleType) -> None:
    ok, _ = gate.evaluate("", ["lsat-static/components/Drill.tsx"])
    assert not ok


def test_empty_body_is_not_mistaken_for_evidence(gate: ModuleType) -> None:
    """A PR opened with no description at all must not slip through."""
    ok, _ = gate.evaluate("", ["frontend/app/(app)/lsat/page.tsx"])
    assert not ok


# --- the gate applies and passes ---------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "Before/after:\n\n![new drill screen](https://example.test/a.png)",
        '<img width="600" src="https://example.test/a.png">',
        (
            "https://github.com/o/r/assets/1/x\n"
            "https://github.com/user-attachments/assets/abc-123"
        ),
        "See docs/images/lsat-drill.png for the new layout.",
    ],
    ids=["markdown", "img-tag", "gh-upload", "repo-path"],
)
def test_body_image_forms_satisfy_the_gate(gate: ModuleType, body: str) -> None:
    ok, message = gate.evaluate(body, ["frontend/components/lsat/Drill.tsx"])
    assert ok, message
    assert "PR body" in message


def test_committed_screenshot_satisfies_the_gate(gate: ModuleType) -> None:
    """The label-free escape hatch: forks cannot label their own PR."""
    ok, message = gate.evaluate(
        "",
        ["frontend/components/lsat/Drill.tsx", "docs/images/lsat-drill-v2.png"],
    )
    assert ok
    assert "committed image" in message


def test_prose_mentioning_a_screenshot_is_not_evidence(gate: ModuleType) -> None:
    """Guards the heuristic's edge: talking about one is not attaching one."""
    ok, _ = gate.evaluate(
        "I took a screenshot and it looks fine, trust me.",
        ["frontend/app/(app)/page.tsx"],
    )
    assert not ok


# --- CLI ---------------------------------------------------------------------


def test_cli_exit_codes(repo_root: Path, tmp_path: Path) -> None:
    """CI reads the exit code, so pin it in both directions."""
    changed = tmp_path / "changed.txt"
    changed.write_text("frontend/components/shell/AppShell.tsx\n")
    script = str(repo_root / "scripts" / "visual_evidence_gate.py")

    failing = subprocess.run(
        [sys.executable, script, "--changed-files", str(changed), "--body", ""],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failing.returncode == 1, failing.stdout
    assert "FAIL" in failing.stdout

    passing = subprocess.run(
        [
            sys.executable,
            script,
            "--changed-files",
            str(changed),
            "--body",
            "![shot](https://example.test/a.png)",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert passing.returncode == 0, passing.stdout
    assert "PASS" in passing.stdout


def test_ci_wires_the_gate_with_a_label_opt_out(repo_root: Path) -> None:
    """A gate nothing calls is just a script."""
    from tests.conftest import require_yaml
    
    yaml = require_yaml()

    ci = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "ci.yml").read_text()
    )
    job = ci["jobs"]["visual-evidence"]
    guard = job["if"]
    assert "needs.changes.outputs.visual" in guard
    assert "no-visual-change" in guard, "the documented opt-out must be wired"
    assert "pull_request" in guard, "a push has no PR body to inspect"
    assert "changes" in job["needs"]
    steps = yaml.dump(job["steps"])
    assert "scripts/visual_evidence_gate.py" in steps
    assert "PR_BODY" in steps, (
        "the body must reach the script through the environment, not shell "
        "interpolation (untrusted input)"
    )


# --- the repo's own default PR body ------------------------------------------


@pytest.fixture(scope="module")
def pr_template(repo_root: Path) -> str:
    return (repo_root / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )


def test_the_untouched_pr_template_is_not_evidence(
    gate: ModuleType, pr_template: str
) -> None:
    """The exact case the gate exists to stop.

    GitHub prefills every PR body with this file verbatim, HTML comments and
    all, and the template's instructions mention ``docs/images/`` twice. While
    the gate matched the raw body, the repo's own default body satisfied it:
    a PR could rewrite every screen, attach nothing, leave the template as
    GitHub wrote it, and pass with exit 0.
    """
    assert "docs/images/" in pr_template, (
        "this test is only meaningful while the template mentions the "
        "directory — if that changed, the regression it guards changed too"
    )
    ok, message = gate.evaluate(
        pr_template, ["frontend/components/shell/AppShell.tsx"]
    )
    assert not ok, (
        "the unmodified PR template passes the gate — the body heuristic is "
        "matching the template's own instructions, not attached evidence"
    )
    assert "no visual evidence" in message


def test_the_template_plus_a_real_attachment_passes(
    gate: ModuleType, pr_template: str
) -> None:
    """Stripping comments must not break the normal case."""
    body = pr_template.replace(
        "| Screen / state | |",
        "| Screen / state | ![shell](https://example.test/shell.png) |",
    )
    ok, _ = gate.evaluate(body, ["frontend/components/shell/AppShell.tsx"])
    assert ok


def test_evidence_hidden_inside_a_comment_does_not_count(gate: ModuleType) -> None:
    """A commented-out image renders as nothing, so it proves nothing."""
    ok, _ = gate.evaluate(
        "<!-- ![old](https://example.test/old.png) -->",
        ["frontend/app/(app)/page.tsx"],
    )
    assert not ok


def test_an_unterminated_comment_swallows_the_rest(gate: ModuleType) -> None:
    """GitHub renders nothing after an unclosed `<!--`, and neither do we."""
    ok, _ = gate.evaluate(
        "<!-- forgot to close\n![shot](https://example.test/a.png)",
        ["frontend/app/(app)/page.tsx"],
    )
    assert not ok


def test_the_directory_alone_is_not_a_screenshot(gate: ModuleType) -> None:
    """`docs/images/` names a folder; only a file in it is evidence."""
    bare, _ = gate.evaluate(
        "Screenshots live under docs/images/ as usual.",
        ["frontend/app/(app)/page.tsx"],
    )
    assert not bare

    named, _ = gate.evaluate(
        "See docs/images/shell-2026-09.png.",
        ["frontend/app/(app)/page.tsx"],
    )
    assert named
