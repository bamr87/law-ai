"""Tests for lawgraph.eval.coverage_audit (spec 018 T-003)."""

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
        <package name="lawgraph">
            <classes>
                <class name="lawgraph/core/autonomy.py" filename="lawgraph/core/autonomy.py"
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
                <class name="lawgraph/eval/loaders.py" filename="lawgraph/eval/loaders.py"
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
                <class name="lawgraph/eval/__init__.py" filename="lawgraph/eval/__init__.py"
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
        from lawgraph.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=40.0, module="x")
        assert r.severity == "high"

    def test_severity_med(self) -> None:
        from lawgraph.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=68.0, module="x")
        assert r.severity == "med"

    def test_severity_ok(self) -> None:
        from lawgraph.eval.coverage_audit import CoverageRecord

        r = CoverageRecord(pct=80.0, module="x")
        assert r.severity == "ok"

    def test_sortable_by_pct(self) -> None:
        from lawgraph.eval.coverage_audit import CoverageRecord

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
        from lawgraph.eval.coverage_audit import load_coverage_report

        result = load_coverage_report(tmp_path / "nonexistent.xml")
        assert result == []

    def test_parses_xml_and_returns_sorted_records(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        records = load_coverage_report(xml_path)

        # Two classes with ≥5 statements; __init__.py has 1 → filtered
        assert len(records) == 2
        # Sorted ascending: 55% first
        assert records[0].pct == pytest.approx(55.0)
        assert records[1].pct == pytest.approx(90.0)

    def test_missing_lines_captured(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        records = load_coverage_report(xml_path)

        # loaders.py record (55%) should have missing lines 2,4,5,8
        loaders_rec = next(r for r in records if "loaders" in r.module)
        assert 2 in loaders_rec.missing_lines
        assert 4 in loaders_rec.missing_lines

    def test_min_statements_filter(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        _write_coverage_xml(xml_path, _MINIMAL_XML)

        # With min_statements=20 both classes should be filtered out
        records = load_coverage_report(xml_path, min_statements=20)
        assert records == []

    def test_returns_empty_on_malformed_xml(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import load_coverage_report

        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text("<<invalid xml>>", encoding="utf-8")

        records = load_coverage_report(xml_path)
        assert records == []


# ---------------------------------------------------------------------------
# overall_coverage
# ---------------------------------------------------------------------------


class TestOverallCoverage:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import overall_coverage

        assert overall_coverage(tmp_path / "no.xml") is None

    def test_parses_root_line_rate(self, tmp_path: Path) -> None:
        from lawgraph.eval.coverage_audit import overall_coverage

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

    These tests load scripts/evolve_audit.py via importlib. They are skipped
    inside Docker where the repo root scripts/ directory is not mounted.
    """

    def _load_ea(self) -> object:
        """Load evolve_audit as a module from its filesystem path."""
        import importlib.util
        import sys
        from pathlib import Path

        # Test file is at backend/tests/eval/test_coverage_audit.py.
        # Repo root is 3 parents up from the test file's backend/ anchor.
        ea_path = Path(__file__).resolve().parents[3] / "scripts" / "evolve_audit.py"
        if not ea_path.exists():
            pytest.skip(
                f"scripts/evolve_audit.py not found at {ea_path} — "
                "skipping (not mounted in Docker)"
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
        import lawgraph.eval.coverage_audit as ca

        monkeypatch.setattr(ca, "_DEFAULT_XML", tmp_path / "missing.xml")
        ea = self._load_ea()
        result = ea._scan_coverage()  # type: ignore[attr-defined]
        assert result == []

    def test_below_threshold_yields_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import lawgraph.eval.coverage_audit as ca

        low_cov_xml = """\
<?xml version="1.0" ?>
<coverage line-rate="0.50" branch-rate="0" version="7.0" timestamp="1234567890">
    <packages>
        <package name="lawgraph">
            <classes>
                <class name="lawgraph/core/x.py" filename="lawgraph/core/x.py"
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
