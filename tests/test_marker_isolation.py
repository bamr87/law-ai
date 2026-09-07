"""The integration-marker isolation contract (BL-20260526-02, spec 014 AC-5).

`make test-backend` and `.github/workflows/ci.yml` both run `-m "not
integration"`, and `integration-tests.yml` runs `-m integration`. Nothing
enforced that split: it rested entirely on each file remembering to declare
`pytestmark = pytest.mark.integration` at module level. A new
`test_*_integration.py` that forgot would leak into every PR run and start
demanding a live Neo4j there — the failure mode is a red CI on a machine that
was never supposed to need databases.

This is the cheap static half: parse each integration test module with `ast`
and assert the marker is actually declared. Stdlib only, so it runs in the
`smoke` tier on a bare runner — which is exactly where a missing marker would
otherwise be discovered the expensive way. The dynamic half (a real
`--collect-only` proving zero items are selected) lives in
`backend/tests/test_marker_isolation.py`, where a pytest runner exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

#: The file spec 014 AC-5 names explicitly; it must exist, or this whole
#: contract is being enforced against nothing.
ANCHOR = "test_citation_resolver_integration.py"


def _integration_modules(backend_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in (backend_dir / "tests").rglob("test_*.py")
        if "integration" in p.stem
    )


def _declares_integration_marker(tree: ast.Module) -> bool:
    """True when a module-level `pytestmark` names `pytest.mark.integration`.

    Accepts the two shapes in use: a bare `pytest.mark.integration` and a list
    of markers containing it.
    """

    def names(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Attribute):
            return [node.attr]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [n for element in node.elts for n in names(element)]
        return []

    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets
        ):
            continue
        if node.value is not None and "integration" in names(node.value):
            return True
    return False


def test_the_anchor_file_still_exists(backend_dir: Path) -> None:
    """AC-5 names one file; if it is gone, this gate guards nothing."""
    matches = [p for p in _integration_modules(backend_dir) if p.name == ANCHOR]
    assert matches, f"{ANCHOR} not found under backend/tests/"


def test_every_integration_module_declares_the_marker(backend_dir: Path) -> None:
    modules = _integration_modules(backend_dir)
    assert modules, "no integration test modules found — has the layout moved?"

    missing = [
        str(path.relative_to(backend_dir))
        for path in modules
        if not _declares_integration_marker(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )
    ]
    assert not missing, (
        "these modules would leak into `make test-backend` and CI's "
        "`-m 'not integration'` run; add a module-level "
        "`pytestmark = pytest.mark.integration`: " + ", ".join(missing)
    )


def test_ci_still_runs_the_default_suite_with_the_marker_filter(
    repo_root: Path,
) -> None:
    """The gate is only worth anything while CI actually deselects."""
    ci = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'not integration' in ci, (
        "ci.yml no longer deselects integration tests — either the contract "
        "changed or the marker filter was dropped by accident"
    )
