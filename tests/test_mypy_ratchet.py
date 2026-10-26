"""Host-side coverage of ``scripts/mypy_ratchet.py`` (BL-20260429-04).

The ratchet is what let CI drop ``continue-on-error`` from ``mypy law_ai
--strict``: it is the only thing standing between "the strict count may not
grow" and a silently-rotting gate. It has to be tested somewhere, and it cannot
be tested in the backend suite — it is a host stdlib script, like
``ux_audit.py`` and the fleet's spec gate, so it lives here with the rest of
the repo-wide checks.

Stdlib + pytest only, per ``tests/conftest.py``: nothing here imports Django,
mypy, or anything from ``backend/``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parent.parent
RATCHET = REPO_ROOT / "scripts" / "mypy_ratchet.py"
BASELINE = REPO_ROOT / "backend" / "mypy-baseline.txt"


def _load_ratchet() -> Any:
    assert RATCHET.is_file(), f"missing {RATCHET}"
    spec = importlib.util.spec_from_file_location("_mypy_ratchet_root", RATCHET)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mypy_ratchet_root"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ratchet() -> Any:
    return _load_ratchet()


REPORT = """\
law_ai/lsat/urls.py:31: error: Function is missing a type annotation  [no-untyped-def]
law_ai/lsat/urls.py:44: error: Function is missing a type annotation  [no-untyped-def]
law_ai/lsat/urls.py:44: note: Use "-> None" if the function does not return a value
law_ai/core/tasks.py:8: error: Skipping analyzing "celery"  [import-untyped]
pyproject.toml: note: unused section(s): module = ['crewai.*']
Found 3 errors in 2 files (checked 78 source files)
"""


class TestParsing:
    def test_counts_errors_per_file_and_ignores_notes(self, ratchet: Any) -> None:
        assert ratchet.parse_report(REPORT) == {
            "law_ai/lsat/urls.py": 2,
            "law_ai/core/tasks.py": 1,
        }

    def test_ignores_the_pathless_config_note(self, ratchet: Any) -> None:
        """`warn_unused_configs` emits a `pyproject.toml: note:` line."""
        assert "pyproject.toml" not in ratchet.parse_report(REPORT)

    def test_accepts_column_numbers(self, ratchet: Any) -> None:
        line = "law_ai/a.py:3:12: error: Bad  [misc]"
        assert ratchet.parse_report(line) == {"law_ai/a.py": 1}

    def test_baseline_round_trips(self, ratchet: Any) -> None:
        counts = {"law_ai/b.py": 1, "law_ai/a.py": 4}
        assert ratchet.parse_baseline(ratchet.render_baseline(counts)) == counts

    def test_rendered_baseline_records_the_total(self, ratchet: Any) -> None:
        rendered = ratchet.render_baseline({"law_ai/a.py": 4, "law_ai/b.py": 1})
        assert "# total: 5" in rendered

    def test_malformed_baseline_line_is_rejected(self, ratchet: Any) -> None:
        with pytest.raises(ValueError):
            ratchet.parse_baseline("not-a-count law_ai/a.py\n")


class TestCompare:
    def test_holding_steady_passes(self, ratchet: Any) -> None:
        base = {"law_ai/a.py": 2}
        failures, slack = ratchet.compare({"law_ai/a.py": 2}, base)
        assert failures == []
        assert slack == []

    def test_growth_in_a_known_file_fails(self, ratchet: Any) -> None:
        failures, _ = ratchet.compare({"law_ai/a.py": 3}, {"law_ai/a.py": 2})
        assert any("baseline allows 2" in f for f in failures)

    def test_a_file_absent_from_the_baseline_fails(self, ratchet: Any) -> None:
        failures, _ = ratchet.compare({"law_ai/new.py": 1}, {"law_ai/a.py": 2})
        assert any("law_ai/new.py" in f for f in failures)

    def test_total_regression_is_reported_first(self, ratchet: Any) -> None:
        failures, _ = ratchet.compare({"law_ai/a.py": 5}, {"law_ai/a.py": 2})
        assert failures[0].startswith("total strict errors 5 exceeds baseline 2")

    def test_improvement_is_slack_not_failure(self, ratchet: Any) -> None:
        failures, slack = ratchet.compare({"law_ai/a.py": 1}, {"law_ai/a.py": 2})
        assert failures == []
        assert any("law_ai/a.py" in s for s in slack)

    def test_a_cleared_file_is_slack_not_failure(self, ratchet: Any) -> None:
        failures, slack = ratchet.compare({}, {"law_ai/a.py": 2})
        assert failures == []
        assert any("now clean" in s for s in slack)


class TestCli:
    def test_check_passes_against_its_own_baseline(
        self, ratchet: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = tmp_path / "report.txt"
        report.write_text(REPORT, encoding="utf-8")
        baseline = tmp_path / "baseline.txt"

        assert (
            ratchet.main(
                ["--report", str(report), "--baseline", str(baseline), "--update"]
            )
            == 0
        )
        assert baseline.is_file()
        assert ratchet.main(["--report", str(report), "--baseline", str(baseline)]) == 0
        assert "OK" in capsys.readouterr().out

    def test_check_fails_on_a_regression(self, ratchet: Any, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline.txt"
        baseline.write_text(
            ratchet.render_baseline({"law_ai/lsat/urls.py": 1}), encoding="utf-8"
        )
        report = tmp_path / "report.txt"
        report.write_text(REPORT, encoding="utf-8")
        assert ratchet.main(["--report", str(report), "--baseline", str(baseline)]) == 1

    def test_missing_baseline_with_errors_is_a_usage_error(
        self, ratchet: Any, tmp_path: Path
    ) -> None:
        report = tmp_path / "report.txt"
        report.write_text(REPORT, encoding="utf-8")
        assert (
            ratchet.main(
                ["--report", str(report), "--baseline", str(tmp_path / "nope.txt")]
            )
            == 2
        )

    def test_missing_baseline_with_a_clean_report_passes(
        self, ratchet: Any, tmp_path: Path
    ) -> None:
        report = tmp_path / "report.txt"
        report.write_text("Success: no issues found in 78 source files\n", "utf-8")
        assert (
            ratchet.main(
                ["--report", str(report), "--baseline", str(tmp_path / "nope.txt")]
            )
            == 0
        )


class TestCommittedBaseline:
    """The shipped baseline has to stay parseable and honest."""

    def test_exists_and_parses(self, ratchet: Any) -> None:
        assert BASELINE.is_file(), f"missing {BASELINE}"
        counts = ratchet.parse_baseline(BASELINE.read_text(encoding="utf-8"))
        assert counts, "an empty baseline means the ratchet should be deleted"
        assert all(value > 0 for value in counts.values())

    def test_header_total_matches_the_entries(self, ratchet: Any) -> None:
        text = BASELINE.read_text(encoding="utf-8")
        counts = ratchet.parse_baseline(text)
        assert f"# total: {sum(counts.values())}" in text

    def test_paths_are_backend_relative_and_real(self) -> None:
        text = BASELINE.read_text(encoding="utf-8")
        paths = [
            line.split("\t", 1)[1].strip()
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert paths
        for path in paths:
            assert path.startswith("law_ai/"), path
            assert (REPO_ROOT / "backend" / path).is_file(), path


class TestGateWiring:
    """The ratchet only matters if CI and the Makefile actually run it."""

    def test_ci_typechecks_without_continue_on_error(self) -> None:
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
        assert "mypy_ratchet.py" in ci
        assert "continue-on-error: true # tighten once strict-clean" not in ci

    def test_makefile_wires_both_directions(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "mypy_ratchet.py" in makefile
        assert "mypy-baseline:" in makefile

    def test_mypy_config_loads_the_django_and_drf_plugins(self) -> None:
        pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text("utf-8")
        assert "mypy_django_plugin.main" in pyproject
        assert "mypy_drf_plugin.main" in pyproject
        assert "django-stubs" in pyproject
        assert "djangorestframework-stubs" in pyproject
