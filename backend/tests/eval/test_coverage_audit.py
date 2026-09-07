"""Tests for law_ai.eval.coverage_audit (spec 018 T-003)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_coverage_xml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")


_MINIMAL_XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.82" branch-rate="0" version="7.0" timestamp="1234567890">
    <packages>
        <package name="law_ai">
            <classes>
                <class name="law_ai/core/autonomy.py" filename="law_ai/core/autonomy.py"
                       line-rate="0.90" branch-rate="0" complexity="0">
                    <lines>
                        <line number="10" hits="1"/>
                        <line number="11" hits="0"/>
                        <line number="12" hits="1"/>
                        <line number="13" hits="1"/>
                        <line number="14" hits="1"/>
                        <line number="15" hits="0"/>
                        <line number="16" hits="1"/>
                        <line number="17" hits="1"/>
                        <line number="18" hits="1"/>
                        <line number="19" hits="1"/>
                    </lines>
                </class>
                <class name="law_ai/eval/loaders.py" filename="law_ai/eval/loaders.py"
                       line-rate="0.55" branch-rate="0" complexity="0">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="0"/>
                        <line number="3" hits="1"/>
                        <line number="4" hits="0"/>
                        <line number="5" hits="0"/>
                        <line number="6" hits="1"/>
                        <line number="7" hits="1"/>
                        <line number="8" hits="0"/>
                        <line number="9" hits="1"/>
                        <line number="10" hits="1"/>
                    </lines>
                </class>
                <class name="law_ai/eval/__init__.py" filename="law_ai/eval/__init__.py"
                       line-rate="1.0" branch-rate="0" complexity="0">
                    <lines>
                        <line number="1" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""


# ---------------------------------------------------------------------------
# CoverageRecord
# ---------------------------------------------------------------------------


class TestCoverageRecord:
    def test_severity_high(self) -> None:
        from law_ai.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=40.0, module="x")
        assert r.severity == "high"

    def test_severity_med(self) -> None:
        from law_ai.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=68.0, module="x")
        assert r.severity == "med"

    def test_severity_ok(self) -> None:
        from law_ai.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=80.0, module="x")
        assert r.severity == "ok"

    def test_sortable_by_pct(self) -> None:
        from law_ai.eval.coverage_audit import CoverageRecord

        records = [
            CoverageRecord(pct=80.0, module="a"),
            CoverageRecord(pct=40.0, module="b"),
        ]
        assert sorted(records)[0].module == "b"


# ---------------------------------------------------------------------------
# load_coverage_report
# ---------------------------------------------------------------------------


class TestLoadCoverageReport:
    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import load_coverage_report

        result = load_coverage_report(tmp_path / "nonexistent.xml")
        assert result == []

    def test_parses_xml_and_returns_sorted_records(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        records = load_coverage_report(xml_path)

        # Two classes with ≥5 statements; __init__.py has 1 → filtered
        assert len(records) == 2
        # Sorted ascending: 55% first
        assert records[0].pct == pytest.approx(55.0)
        assert records[1].pct == pytest.approx(90.0)

    def test_missing_lines_captured(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        records = load_coverage_report(xml_path)

        # loaders.py record (55%) should have missing lines 2,4,5,8
        loaders_rec = next(r for r in records if "loaders" in r.module)
        assert 2 in loaders_rec.missing_lines
        assert 4 in loaders_rec.missing_lines

    def test_min_statements_filter(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        # With min_statements=20 both classes should be filtered out
        records = load_coverage_report(xml_path, min_statements=20)
        assert records == []

    def test_returns_empty_on_malformed_xml(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text("<<invalid xml>>", encoding="utf-8")

        records = load_coverage_report(xml_path)
        assert records == []


# ---------------------------------------------------------------------------
# overall_coverage
# ---------------------------------------------------------------------------


class TestOverallCoverage:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import overall_coverage

        assert overall_coverage(tmp_path / "no.xml") is None

    def test_parses_root_line_rate(self, tmp_path: Path) -> None:
        from law_ai.eval.coverage_audit import overall_coverage

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        total = overall_coverage(xml_path)
        assert total == pytest.approx(82.0)


# ---------------------------------------------------------------------------
# evolve_audit integration — _scan_coverage shim
# ---------------------------------------------------------------------------


class TestEvolveAuditScanCoverage:
    """Verify that the updated _scan_coverage in evolve_audit.py delegates to
    coverage_audit and returns the expected Candidate type.

    These tests load scripts/evolve_audit.py via importlib. They used to skip
    inside Docker on the premise that the repo root was not mounted — false
    since docker-compose mounts ``./:/repo`` into the backend and worker
    services, so both tests silently never ran in ``make test-backend``
    (BL-20260511-14). ``_load_ea`` now tries every place the script can be.
    """

    def _load_ea(self) -> object:
        """Load evolve_audit as a module from its filesystem path."""
        import importlib.util
        import os
        import sys
        from pathlib import Path

        # Test file is at backend/tests/eval/test_coverage_audit.py.
        #   1. Host / venv run: three parents up from the backend/ anchor.
        #   2. Docker: the repo is bind-mounted at /repo (docker-compose.yml),
        #      while the test file lives at /app/tests/... where parents[3]
        #      is "/" — which is why this used to skip.
        #   3. An explicit override for any other layout.
        candidates = [
            Path(__file__).resolve().parents[3] / "scripts" / "evolve_audit.py",
            Path("/repo/scripts/evolve_audit.py"),
        ]
        override = os.getenv("LAW_AI_REPO_ROOT", "").strip()
        if override:
            candidates.insert(0, Path(override) / "scripts" / "evolve_audit.py")

        ea_path = next((p for p in candidates if p.exists()), None)
        if ea_path is None:
            pytest.skip(
                "scripts/evolve_audit.py not found in any of "
                f"{[str(p) for p in candidates]} — set LAW_AI_REPO_ROOT"
            )
        spec = importlib.util.spec_from_file_location("_evolve_audit_test", ea_path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_evolve_audit_test"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_no_xml_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import law_ai.eval.coverage_audit as ca

        monkeypatch.setattr(ca, "_DEFAULT_XML", tmp_path / "missing.xml")
        ea = self._load_ea()
        result = ea._scan_coverage()  # type: ignore[attr-defined]
        assert result == []

    def test_below_threshold_yields_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import law_ai.eval.coverage_audit as ca

        low_cov_xml = """\
<?xml version="1.0" ?>
<coverage line-rate="0.50" branch-rate="0" version="7.0" timestamp="1234567890">
    <packages>
        <package name="law_ai">
            <classes>
                <class name="law_ai/core/x.py" filename="law_ai/core/x.py"
                       line-rate="0.50" branch-rate="0" complexity="0">
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="0"/>
                        <line number="3" hits="1"/>
                        <line number="4" hits="0"/>
                        <line number="5" hits="0"/>
                        <line number="6" hits="1"/>
                        <line number="7" hits="1"/>
                        <line number="8" hits="0"/>
                        <line number="9" hits="1"/>
                        <line number="10" hits="1"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(textwrap.dedent(low_cov_xml), encoding="utf-8")
        monkeypatch.setattr(ca, "_DEFAULT_XML", xml_path)

        ea = self._load_ea()
        candidates = ea._scan_coverage()  # type: ignore[attr-defined]
        assert len(candidates) == 1
        assert candidates[0].severity == "high"
        assert "50" in candidates[0].title


class TestEvolveAuditScanLegalbench:
    """``_scan_legalbench`` (BL-20260511-15).

    This scanner is load-bearing and was untested: ``main()`` wires it in and
    ``.github/workflows/nightly-tests.yml`` greps the audit output for
    ``*, high*`` to fail the run, so a silent break here silently stops
    failing the nightly on a benchmark regression.

    ``_load_ea`` is borrowed from the class above rather than copied, so the
    Docker path fix has one home. The bullet that asked for this said
    ``report-*.json``; the
    writer actually names reports ``<UTC-timestamp>.json``
    (``law_ai/eval/legalbench.py``) and the scanner globs ``*.json`` minus
    ``baseline.json``, so the fixtures below use the real names.
    """

    _load_ea = TestEvolveAuditScanCoverage._load_ea

    @staticmethod
    def _seed(ea: object, tmp_path: Path, name: str, payload: dict) -> None:
        import json as _json

        report_dir = tmp_path / "backend" / "var" / "legalbench"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / name).write_text(_json.dumps(payload), encoding="utf-8")
        # A real directory always has one; it must be excluded from the glob.
        (report_dir / "baseline.json").write_text(
            _json.dumps({"accuracies": {"precedent_retrieval": 0.8}}), encoding="utf-8"
        )
        ea.REPO = tmp_path  # type: ignore[attr-defined]

    def test_no_reports_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ea = self._load_ea()
        monkeypatch.setattr(ea, "REPO", tmp_path, raising=False)
        assert ea._scan_legalbench() == []  # type: ignore[attr-defined]

    def test_negative_delta_yields_a_high_severity_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ea = self._load_ea()
        self._seed(
            ea,
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

        candidates = ea._scan_legalbench()  # type: ignore[attr-defined]

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.severity == "high"
        assert candidate.kind == "test-gap"
        assert "precedent_retrieval" in candidate.rationale
        assert "-10.0pp" in candidate.rationale
        # The nightly greps the rendered bullet for "*, high*" — the severity
        # has to survive into the text, not just the dataclass.
        assert "high" in candidate.severity

    def test_a_positive_delta_is_not_a_regression(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ea = self._load_ea()
        self._seed(
            ea,
            tmp_path,
            "20260901T000000Z.json",
            {
                "delta": {
                    "precedent_retrieval": {
                        "before": 0.7,
                        "after": 0.8,
                        "delta_pp": 10.0,
                    }
                }
            },
        )
        assert ea._scan_legalbench() == []  # type: ignore[attr-defined]

    def test_only_the_newest_report_is_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An old regression must not keep failing every later nightly."""
        ea = self._load_ea()
        self._seed(
            ea,
            tmp_path,
            "20260801T000000Z.json",
            {"delta": {"abercrombie": {"delta_pp": -20.0}}},
        )
        self._seed(
            ea,
            tmp_path,
            "20260901T000000Z.json",
            {"delta": {"abercrombie": {"delta_pp": 1.0}}},
        )
        assert ea._scan_legalbench() == []  # type: ignore[attr-defined]

    def test_a_malformed_report_is_ignored_rather_than_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ea = self._load_ea()
        report_dir = tmp_path / "backend" / "var" / "legalbench"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "20260901T000000Z.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(ea, "REPO", tmp_path, raising=False)

        assert ea._scan_legalbench() == []  # type: ignore[attr-defined]
