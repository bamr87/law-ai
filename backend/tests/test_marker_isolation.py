"""Integration tests contribute zero items to the default run (BL-20260526-02).

Spec 014 AC-5's isolation contract — "`test_citation_resolver_integration`
does not run without `-m integration`" — was enforced by nothing. `ci.yml`
and `make test-backend` pass `-m "not integration"` and `--strict-markers`
rejects *unknown* markers, but neither notices a module that forgot to declare
the marker it needed. Such a module runs in every PR and then demands a live
Neo4j on a runner that has none.

The static half of the gate (parse each `test_*integration*.py` and assert the
module-level `pytestmark`) lives in the root suite, `tests/test_marker_
isolation.py`, so it runs stdlib-only on a bare runner. This is the dynamic
half: an actual nested collection proving the deselection really happens.

The nested run disables coverage and the cache provider deliberately — a child
pytest writing `.coverage` would clobber the parent's data file — and clears
`addopts` so this suite's own `--cov-fail-under` does not follow it in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
#: The file spec 014 AC-5 names.
ANCHOR = BACKEND_ROOT / "tests" / "db" / "test_citation_resolver_integration.py"


def _collect_many(targets: list[str], *marker_args: str) -> list[str]:
    """Return the test ids a `--collect-only` run selects for *targets*."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            *marker_args,
            *targets,
        ],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and line.strip().startswith("tests/")
    ]


def _collect(target: Path, *marker_args: str) -> list[str]:
    """`_collect_many` for a single path."""
    return _collect_many([str(target)], *marker_args)


@pytest.mark.skipif(not ANCHOR.is_file(), reason=f"{ANCHOR.name} has moved")
def test_the_anchor_file_has_tests_to_isolate() -> None:
    """Guard against the gate passing because the file collects nothing."""
    assert _collect(ANCHOR), "no tests collected — the contract guards nothing"


@pytest.mark.skipif(not ANCHOR.is_file(), reason=f"{ANCHOR.name} has moved")
def test_citation_resolver_integration_is_deselected_by_default() -> None:
    """The exact assertion AC-5 asks for."""
    selected = _collect(ANCHOR, "-m", "not integration")
    assert (
        selected == []
    ), "integration tests leaked into the default run: " + ", ".join(selected)


@pytest.mark.skipif(not ANCHOR.is_file(), reason=f"{ANCHOR.name} has moved")
def test_the_same_file_is_selected_with_the_marker() -> None:
    """Deselection must come from the marker, not from a collection error."""
    assert _collect(ANCHOR, "-m", "integration"), (
        "the file collects nothing under -m integration either — its marker "
        "is missing, not just mis-scoped"
    )


def test_no_integration_module_leaks_into_the_default_suite() -> None:
    """Every `test_*integration*.py`, not just the one AC-5 names.

    All of them go into a *single* nested run: one Django setup instead of
    one per file, and collecting the whole `tests/` tree instead would add a
    minute of full-suite collection to `make test-backend` for no extra
    guarantee.
    """
    modules = sorted(
        p.relative_to(BACKEND_ROOT).as_posix()
        for p in (BACKEND_ROOT / "tests").rglob("test_*.py")
        if "integration" in p.stem
    )
    assert modules, "no integration modules found — has the layout moved?"

    selected = _collect_many(modules, "-m", "not integration")
    leaked = sorted({item.split("::", 1)[0] for item in selected})
    assert not leaked, (
        "these modules run in `make test-backend` and would demand live "
        f"databases there: {leaked}"
    )

    # And the same set does collect under the marker, so the emptiness above
    # is deselection rather than a collection error hiding a broken file.
    assert _collect_many(modules, "-m", "integration")
