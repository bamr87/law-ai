"""Host-side coverage of ``scripts/evolve_audit.py`` (BL-20260511-14, -15).

``evolve_audit.py`` is load-bearing: `.github/workflows/nightly-tests.yml`
runs it and greps the output for ``*, high*`` to fail the run, so a silent
break in a scanner silently stops the nightly failing on a regression. Its two
substantive scanners had exactly one test between them, in the backend suite,
and both of those *skipped inside Docker* — which is where the backend suite
runs — so in practice neither had ever executed in CI.

This module is the host tier's copy of that coverage, and ``make lint-specs``
runs it (BL-20260511-14) right after the three stdlib validators — so the
person editing ``scripts/evolve_audit.py`` finds a broken scanner in the same
command that checks their spec, not in a CI run later. That target's recipe
checks for pytest first and explains itself if it is missing; CI's
repo-structural job runs the root suite bare as well, so the gate holds on
both surfaces.

Stdlib + pytest only, per ``tests/conftest.py``: nothing here imports Django
or ``law_ai``. ``_scan_coverage`` reaches for
``sys.modules['law_ai.eval.coverage_audit']`` before loading anything, so a
stub registered under that name is enough to drive it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parent.parent
EVOLVE_AUDIT = REPO_ROOT / "scripts" / "evolve_audit.py"


def _load_evolve_audit() -> Any:
    """Load ``scripts/evolve_audit.py`` as an anonymous module."""
    assert EVOLVE_AUDIT.is_file(), f"missing {EVOLVE_AUDIT}"
    spec = importlib.util.spec_from_file_location("_evolve_audit_root", EVOLVE_AUDIT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_evolve_audit_root"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The script, rooted at a throwaway repo so scans see only fixtures."""
    mod = _load_evolve_audit()
    monkeypatch.setattr(mod, "REPO", tmp_path, raising=False)
    monkeypatch.setattr(mod, "BACKLOG", tmp_path / "BACKLOG.md", raising=False)
    return mod


def _stub_coverage(
    monkeypatch: pytest.MonkeyPatch,
    *,
    overall: float | None,
    records: list[Any] | None = None,
) -> None:
    """Register a fake ``law_ai.eval.coverage_audit`` for the scanner to find.

    `_scan_coverage` prefers an already-imported module of that name so tests
    can patch it (see its docstring), which is exactly the seam that lets this
    host-side test run with no Django and no backend import.
    """

    class _Record:
        def __init__(self, module: str, pct: float) -> None:
            self.module = module
            self.pct = pct

    stub = types.ModuleType("law_ai.eval.coverage_audit")
    stub.overall_coverage = lambda: overall  # type: ignore[attr-defined]
    stub.load_coverage_report = lambda: (  # type: ignore[attr-defined]
        records if records is not None else [_Record("law_ai/core/x.py", 12.0)]
    )
    monkeypatch.setitem(sys.modules, "law_ai.eval.coverage_audit", stub)


# ---------------------------------------------------------------------------
# _scan_coverage
# ---------------------------------------------------------------------------
class TestScanCoverage:
    def test_absent_coverage_data_yields_nothing(
        self, ea: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No coverage.xml is "unknown", not "0%" — it must not file a bug."""
        _stub_coverage(monkeypatch, overall=None)
        assert ea._scan_coverage() == []

    def test_coverage_at_target_yields_nothing(
        self, ea: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_coverage(monkeypatch, overall=83.4)
        assert ea._scan_coverage() == []

    def test_below_the_error_gate_is_severity_high(
        self, ea: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_coverage(monkeypatch, overall=58.0)

        candidates = ea._scan_coverage()

        assert len(candidates) == 1
        assert candidates[0].severity == "high"
        assert candidates[0].kind == "test-gap"
        assert "58" in candidates[0].title
        assert "law_ai/core/x.py" in candidates[0].rationale

    def test_between_the_gates_is_severity_med(
        self, ea: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """65-75% is a warning; only under 65 fails the constitution gate."""
        _stub_coverage(monkeypatch, overall=70.0)

        candidates = ea._scan_coverage()

        assert len(candidates) == 1
        assert candidates[0].severity == "med"


# ---------------------------------------------------------------------------
# _scan_legalbench
# ---------------------------------------------------------------------------
class TestScanLegalbench:
    @staticmethod
    def _seed(tmp_path: Path, name: str, payload: dict[str, Any]) -> None:
        report_dir = tmp_path / "backend" / "var" / "legalbench"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / name).write_text(json.dumps(payload), encoding="utf-8")
        # Every real directory has one, and it must stay out of the glob.
        (report_dir / "baseline.json").write_text(
            json.dumps({"accuracies": {"precedent_retrieval": 0.8}}), encoding="utf-8"
        )

    def test_no_reports_yields_nothing(self, ea: Any, tmp_path: Path) -> None:
        assert ea._scan_legalbench() == []

    def test_a_regression_yields_a_high_severity_candidate(
        self, ea: Any, tmp_path: Path
    ) -> None:
        self._seed(
            tmp_path,
            "20260901T000000Z.json",
            {
                "delta": {
                    "precedent_retrieval": {
                        "before": 0.8,
                        "after": 0.7,
                        "delta_pp": -10.0,
                    }
                }
            },
        )

        candidates = ea._scan_legalbench()

        assert len(candidates) == 1
        assert candidates[0].severity == "high"
        assert candidates[0].kind == "test-gap"
        assert "precedent_retrieval" in candidates[0].rationale
        assert "-10.0pp" in candidates[0].rationale

    def test_an_improvement_is_not_a_regression(
        self, ea: Any, tmp_path: Path
    ) -> None:
        self._seed(
            tmp_path,
            "20260901T000000Z.json",
            {"delta": {"precedent_retrieval": {"delta_pp": 4.0}}},
        )
        assert ea._scan_legalbench() == []

    def test_only_the_newest_report_counts(self, ea: Any, tmp_path: Path) -> None:
        """Otherwise one bad night fails every nightly that follows it."""
        self._seed(
            tmp_path, "20260801T000000Z.json", {"delta": {"a": {"delta_pp": -20.0}}}
        )
        self._seed(
            tmp_path, "20260901T000000Z.json", {"delta": {"a": {"delta_pp": 1.0}}}
        )
        assert ea._scan_legalbench() == []

    def test_a_malformed_report_is_ignored(self, ea: Any, tmp_path: Path) -> None:
        report_dir = tmp_path / "backend" / "var" / "legalbench"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "20260901T000000Z.json").write_text("{not json", encoding="utf-8")

        assert ea._scan_legalbench() == []


# ---------------------------------------------------------------------------
# The nightly's contract with this script
# ---------------------------------------------------------------------------
def test_rendered_bullet_carries_the_severity_the_nightly_greps_for(
    ea: Any, tmp_path: Path
) -> None:
    """`nightly-tests.yml` greps the audit output for ``*, high*``.

    That grep is the only thing that turns a benchmark regression into a red
    run, so the rendered text — not just the dataclass field — has to carry
    the severity.
    """
    TestScanLegalbench._seed(
        tmp_path,
        "20260901T000000Z.json",
        {"delta": {"precedent_retrieval": {"delta_pp": -10.0}}},
    )
    candidate = ea._scan_legalbench()[0]

    bullet = candidate.render("BL-20260901-01")
    assert "*test-gap, high*" in bullet
    assert bullet.startswith("- **BL-20260901-01**")


def test_lint_specs_runs_this_module_on_the_host(repo_root: Path) -> None:
    """BL-20260511-14's second clause: `make lint-specs` has to run these.

    The file existing and passing is only half the ask. Until the target ran
    it, the only place this coverage executed was a CI job — so someone
    editing `scripts/evolve_audit.py` and running the gate they are told to
    run got no signal at all.
    """
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("\nlint-specs:", 1)[1].split("\n\n", 1)[0]
    assert "tests/test_evolve_audit.py" in recipe, (
        "`make lint-specs` no longer runs this module — the gate is back to "
        "three scripts and this coverage is CI-only again"
    )
    assert "pytest" in recipe
    # pytest is the one non-stdlib thing the target needs; a missing
    # interpreter package must produce a sentence, not a traceback.
    assert "import pytest" in recipe, (
        "the recipe must check for pytest and explain itself when it is absent"
    )
