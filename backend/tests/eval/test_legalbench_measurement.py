"""Tests for the LegalBench measurement fixes (BL-20260810-04, spec 031).

Covers the four defects that made the harness unable to support the
constitution §3 "no more than 1 pp regression" policy:

1. CWD-relative paths (reports landed in ``backend/backend/var/...``).
2. Infrastructure failure scored as wrong answers (``accuracy=0.0``).
3. No baseline / no score history.
4. Scoring too weak to handle instruction-tuned model output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from law_ai.eval import paths
from law_ai.eval.legalbench import (
    EvalInfrastructureError,
    LegalBenchConfig,
    baseline_comparability,
    check_regression,
    run_eval,
    update_baseline,
)
from law_ai.eval.scoring import extract_label, score_response

# ---------------------------------------------------------------------------
# 1. Path anchoring
# ---------------------------------------------------------------------------


class TestPathAnchoring:
    def test_cache_root_is_absolute_and_under_backend(self) -> None:
        assert paths.CACHE_ROOT.is_absolute()
        assert (paths.BACKEND_ROOT / "law_ai").is_dir()
        assert paths.CACHE_ROOT.parts[-2:] == ("var", "legalbench")

    def test_no_doubled_backend_segment(self) -> None:
        """Regression: CWD=/app (== backend) made 'backend/var/...' wrong."""
        assert "backend/backend" not in paths.CACHE_ROOT.as_posix()
        assert "backend/backend" not in paths.BASELINE_PATH.as_posix()

    def test_default_report_path_lands_in_the_cache_root(self) -> None:
        config = LegalBenchConfig(subsets=["core_reasoning"], model="m")
        assert config.report_path is not None
        assert config.report_path.parent == paths.CACHE_ROOT


# ---------------------------------------------------------------------------
# 2. Infrastructure failure vs. a real score
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every eval artifact path at the modules that captured them."""
    root = tmp_path / "legalbench"
    root.mkdir(parents=True)
    monkeypatch.setattr(paths, "CACHE_ROOT", root)
    monkeypatch.setattr(paths, "BASELINE_PATH", root / "baseline.json")
    monkeypatch.setattr(paths, "HISTORY_PATH", root / "history.jsonl")
    import law_ai.eval.report as report_mod

    monkeypatch.setattr(report_mod, "BASELINE_PATH", root / "baseline.json")
    monkeypatch.setattr(report_mod, "HISTORY_PATH", root / "history.jsonl")
    return root


def _config(root: Path, **kw: Any) -> LegalBenchConfig:
    return LegalBenchConfig(
        subsets=kw.pop("subsets", ["core_reasoning"]),
        model="test-model",
        report_path=root / "run.json",
        **kw,
    )


class TestInfrastructureFailure:
    def test_total_ollama_failure_raises_instead_of_scoring_zero(
        self, isolated_cache: Path
    ) -> None:
        boom = RuntimeError("Ollama is unreachable at http://ollama:11434")
        with (
            patch("law_ai.eval.legalbench._call_ollama", side_effect=boom),
            pytest.raises(EvalInfrastructureError, match="infrastructure failure"),
        ):
            run_eval(_config(isolated_cache))

    def test_partial_failure_excludes_errored_items_from_accuracy(
        self, isolated_cache: Path
    ) -> None:
        calls = {"n": 0}

        def flaky(prompt: str, **kw: Any) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return "True"
            raise RuntimeError("connection reset")

        with patch("law_ai.eval.legalbench._call_ollama", side_effect=flaky):
            report = run_eval(_config(isolated_cache))

        row = report["subsets"][0]
        assert row["n"] == 2
        assert row["scored"] == 1
        assert row["errored"] == 1
        # 1 correct of 1 that actually ran — not 1/2.
        assert row["accuracy"] == 1.0
        assert any("error" in item for item in row["items"])


# ---------------------------------------------------------------------------
# 3. Baseline, history, regression gate
# ---------------------------------------------------------------------------


class TestBaselineAndHistory:
    def test_history_is_appended_per_run(self, isolated_cache: Path) -> None:
        with patch("law_ai.eval.legalbench._call_ollama", return_value="True"):
            run_eval(_config(isolated_cache))
            run_eval(_config(isolated_cache))

        history = (isolated_cache / "history.jsonl").read_text().strip().splitlines()
        assert len(history) == 2
        first = json.loads(history[0])
        assert "accuracies" in first and "core_reasoning" in first["accuracies"]
        assert first["synthetic"]["core_reasoning"] is True

    def test_refuses_to_baseline_synthetic_stub_data(
        self, isolated_cache: Path
    ) -> None:
        with patch("law_ai.eval.legalbench._call_ollama", return_value="True"):
            report = run_eval(_config(isolated_cache))
        with pytest.raises(EvalInfrastructureError, match="synthetic stub data"):
            update_baseline(report)

    def test_regression_detected_beyond_tolerance(self) -> None:
        report = {
            "delta": {
                "core_reasoning": {"before": 0.80, "after": 0.75, "delta_pp": -5.0},
                "causation": {"before": 0.80, "after": 0.795, "delta_pp": -0.5},
            }
        }
        problems = check_regression(report)
        assert len(problems) == 1
        assert "core_reasoning" in problems[0]

    def test_improvement_is_never_a_regression(self) -> None:
        report = {"delta": {"c": {"before": 0.5, "after": 0.9, "delta_pp": 40.0}}}
        assert check_regression(report) == []


class TestBaselineComparability:
    """BL-20260906-29: a delta across two different models is not a regression."""

    REPORT = {
        "model": "mistral:7b-instruct-q4_K_M",
        "subsets": [
            {"subset": "core_reasoning", "accuracy": 0.75, "scorer": "default_match"}
        ],
        "delta": {"core_reasoning": {"before": 0.80, "after": 0.75, "delta_pp": -5.0}},
    }

    @pytest.fixture()
    def baseline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        import law_ai.eval.legalbench as lb

        path = tmp_path / "baseline.json"
        monkeypatch.setattr(lb, "BASELINE_PATH", path)
        return path

    def _write(self, path: Path, **overrides: Any) -> None:
        payload = {
            "model": "mistral:7b-instruct-q4_K_M",
            "accuracies": {"core_reasoning": 0.80},
            "scorers": {"core_reasoning": "default_match"},
        }
        payload.update(overrides)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_matching_model_and_scorers_still_flags_the_drop(
        self, baseline: Path
    ) -> None:
        self._write(baseline)
        problems = check_regression(dict(self.REPORT))
        assert len(problems) == 1 and "core_reasoning" in problems[0]

    def test_a_different_model_skips_the_comparison(self, baseline: Path) -> None:
        self._write(baseline, model="llama3:8b")
        reasons = baseline_comparability(dict(self.REPORT))
        assert reasons and "llama3:8b" in reasons[0]
        assert check_regression(dict(self.REPORT)) == []

    def test_a_different_scorer_skips_the_comparison(self, baseline: Path) -> None:
        self._write(baseline, scorers={"core_reasoning": "yes_no"})
        reasons = baseline_comparability(dict(self.REPORT))
        assert reasons and "yes_no" in reasons[0]
        assert check_regression(dict(self.REPORT)) == []

    def test_a_legacy_bare_baseline_claims_nothing_and_stays_comparable(
        self, baseline: Path
    ) -> None:
        baseline.write_text(json.dumps({"core_reasoning": 0.80}), encoding="utf-8")
        assert baseline_comparability(dict(self.REPORT)) == []
        assert len(check_regression(dict(self.REPORT))) == 1


# ---------------------------------------------------------------------------
# 4. Scoring strength
# ---------------------------------------------------------------------------


class TestScoring:
    @pytest.mark.parametrize(
        "response,expected",
        [
            ("True", "True"),
            ("true.", "True"),
            ("The answer is True.", "True"),
            ("Answer: yes", "Yes"),
            ("  YES  ", "Yes"),
        ],
    )
    def test_accepts_verbose_but_correct_answers(
        self, response: str, expected: str
    ) -> None:
        ok, _ = score_response(response, expected, "core_reasoning")
        assert ok is True

    @pytest.mark.parametrize(
        "response,expected",
        [
            ("False", "True"),
            # The later "true" must NOT rescue a leading "False".
            ("False — it is not true that the offer stands.", "True"),
            ("", "True"),
            ("I cannot determine this.", "True"),
        ],
    )
    def test_rejects_wrong_answers(self, response: str, expected: str) -> None:
        ok, _ = score_response(response, expected, "core_reasoning")
        assert ok is False

    def test_free_text_subsets_do_not_use_label_extraction(self) -> None:
        """Closed-vocabulary extraction never fires on a case name.

        Spec 031 asserted here that a prose-prefixed case name scored *wrong*.
        BL-20260811-11 replaced that floor for `precedent_retrieval` with a
        recall scorer — naming the right case in a sentence is a hit, naming
        the wrong one is still a miss — so the assertion moved with it. What
        has not changed is that `extract_label` stays out of free-text tasks.
        """
        ok, _ = score_response(
            "The case is International Shoe Co. v. Washington",
            "International Shoe Co. v. Washington",
            "precedent_retrieval",
        )
        assert ok is True
        ok, _ = score_response(
            "The case is Erie Railroad Co. v. Tompkins",
            "International Shoe Co. v. Washington",
            "precedent_retrieval",
        )
        assert ok is False
        assert extract_label("The case is International Shoe") is None
