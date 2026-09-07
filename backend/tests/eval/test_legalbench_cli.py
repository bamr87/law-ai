"""Tests for the LegalBench evaluation harness (spec 018 T-002)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# LegalBenchConfig
# ---------------------------------------------------------------------------


class TestLegalBenchConfig:
    def test_valid_subsets_accepted(self) -> None:
        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(subsets=["core_reasoning"])
        assert cfg.subsets == ["core_reasoning"]

    def test_unknown_subset_raises(self) -> None:
        from law_ai.eval.legalbench import LegalBenchConfig

        with pytest.raises(ValueError, match="Unknown LegalBench subset"):
            LegalBenchConfig(subsets=["totally_fake_task"])

    def test_default_model_from_settings(self, settings: Any) -> None:
        from django.conf import settings as dj

        dj.OLLAMA_DEFAULT_MODEL = "llama3.1:8b-instruct-q4_K_M"
        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(subsets=["definitions"])
        assert cfg.model == "llama3.1:8b-instruct-q4_K_M"

    def test_explicit_model_overrides_settings(self) -> None:
        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(subsets=["core_reasoning"], model="phi3:mini")
        assert cfg.model == "phi3:mini"

    def test_default_report_path_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(subsets=["causation"])
        assert cfg.report_path is not None
        assert cfg.report_path.suffix == ".json"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


class TestLoaders:
    @pytest.fixture()
    def empty_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the loader at a directory with nothing in it (BL-20260906-32).

        Without this these two tests read `backend/var/legalbench/` on any
        machine that has run `make legalbench-cache`, so "when no cache" was
        measuring whatever the developer had fetched.
        """
        from law_ai.eval import loaders

        monkeypatch.setattr(
            loaders,
            "subset_cache_path",
            lambda subset: tmp_path / subset / "items.jsonl",
        )
        return tmp_path

    def test_load_synthetic_stub_when_no_cache(self, empty_cache: Path) -> None:
        from law_ai.eval.loaders import is_synthetic, load_task

        assert is_synthetic("core_reasoning") is True
        items = load_task("core_reasoning")
        assert len(items) >= 1
        # The stub, not the dataset: every fixture index is marked as one.
        assert all(str(item["index"]).startswith("stub-") for item in items)
        for item in items:
            assert "text" in item
            assert "answer" in item

    def test_limit_is_respected(self, empty_cache: Path) -> None:
        from law_ai.eval.loaders import load_task

        assert len(load_task("core_reasoning")) > 1
        items = load_task("core_reasoning", limit=1)
        assert len(items) == 1

    def test_unknown_subset_raises(self) -> None:
        from law_ai.eval.loaders import load_task

        with pytest.raises(ValueError, match="Unknown subset"):
            load_task("bad_subset")

    def test_load_from_jsonl_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange — create a fake JSONL cache
        cache_dir = tmp_path / "core_reasoning"
        cache_dir.mkdir()
        items_file = cache_dir / "items.jsonl"
        items_file.write_text(
            textwrap.dedent("""\
                {"index": 0, "text": "Q1?", "answer": "Yes"}
                {"index": 1, "text": "Q2?", "answer": "No"}
                # this is a comment line and should be skipped
                {"index": 2, "text": "Q3?", "answer": "True"}
            """),
            encoding="utf-8",
        )
        # Paths are now anchored in law_ai.eval.paths (spec 031), so redirect
        # the helper the loader calls rather than a module-level constant.
        import law_ai.eval.loaders as loaders_module

        monkeypatch.setattr(
            loaders_module,
            "subset_cache_path",
            lambda subset: tmp_path / subset / "items.jsonl",
        )

        items = loaders_module.load_task("core_reasoning")
        assert len(items) == 3
        assert items[0]["answer"] == "Yes"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_exact_match(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response("True", "True", "core_reasoning")
        assert ok is True

    def test_case_insensitive_match(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response("TRUE", "true", "core_reasoning")
        assert ok is True

    def test_prefix_match(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response(
            "True, because the mailbox rule applies.", "True", "core_reasoning"
        )
        assert ok is True

    def test_first_word_match_with_punctuation(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response("Yes.", "Yes", "definitions")
        assert ok is True

    def test_no_match(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response("False", "True", "core_reasoning")
        assert ok is False

    def test_empty_response_does_not_match(self) -> None:
        from law_ai.eval.scoring import score_response

        ok, _ = score_response("", "True", "core_reasoning")
        assert ok is False


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


class TestReport:
    def test_write_report_creates_file(self, tmp_path: Path) -> None:
        from law_ai.eval.legalbench import LegalBenchConfig
        from law_ai.eval.report import write_report

        report_path = tmp_path / "report.json"
        cfg = LegalBenchConfig(subsets=["core_reasoning"], report_path=report_path)
        subset_results = [
            {
                "subset": "core_reasoning",
                "n": 2,
                "correct": 1,
                "accuracy": 0.5,
                "items": [],
            }
        ]
        write_report(subset_results, config=cfg)

        assert report_path.exists()
        loaded = json.loads(report_path.read_text())
        assert loaded["run_id"] == cfg.run_id
        assert loaded["subsets"][0]["accuracy"] == 0.5

    def test_delta_computed_from_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import law_ai.eval.report as report_module

        monkeypatch.setattr(report_module, "BASELINE_PATH", tmp_path / "baseline.json")
        monkeypatch.setattr(report_module, "HISTORY_PATH", tmp_path / "history.jsonl")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"core_reasoning": 0.70}), encoding="utf-8")

        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(
            subsets=["core_reasoning"], report_path=tmp_path / "rep.json"
        )
        subset_results = [
            {
                "subset": "core_reasoning",
                "n": 10,
                "correct": 8,
                "accuracy": 0.80,
                "items": [],
            }
        ]
        report = report_module.write_report(subset_results, config=cfg)

        assert "delta" in report
        assert report["delta"]["core_reasoning"]["delta_pp"] == pytest.approx(
            10.0, abs=0.01
        )

    def test_no_delta_when_baseline_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import law_ai.eval.report as report_module

        monkeypatch.setattr(report_module, "BASELINE_PATH", tmp_path / "baseline.json")
        monkeypatch.setattr(report_module, "HISTORY_PATH", tmp_path / "history.jsonl")

        from law_ai.eval.legalbench import LegalBenchConfig

        cfg = LegalBenchConfig(
            subsets=["core_reasoning"], report_path=tmp_path / "rep.json"
        )
        report = report_module.write_report(
            [
                {
                    "subset": "core_reasoning",
                    "n": 5,
                    "correct": 3,
                    "accuracy": 0.6,
                    "items": [],
                }
            ],
            config=cfg,
        )
        assert "delta" not in report


# ---------------------------------------------------------------------------
# run_eval — integrated end-to-end (Ollama mocked)
# ---------------------------------------------------------------------------


class TestRunEval:
    def test_run_eval_returns_report_dict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_eval executes end-to-end with Ollama stubbed out.

        The cache path is redirected at an empty temp dir so the loader falls
        back to its synthetic stubs deterministically: once `make
        legalbench-cache` (BL-20260811-09) has run, `backend/var/legalbench/`
        holds the real items and this assertion would otherwise depend on
        whether the developer had fetched the dataset.
        """
        from law_ai.eval import loaders
        from law_ai.eval.legalbench import LegalBenchConfig, run_eval

        monkeypatch.setattr(
            loaders,
            "subset_cache_path",
            lambda subset: tmp_path / subset / "items.jsonl",
        )
        report_path = tmp_path / "run.json"
        cfg = LegalBenchConfig(
            subsets=["definitions"],
            model="stub-model",
            limit=1,
            report_path=report_path,
        )

        # Stub Ollama to return the expected answer
        with patch("law_ai.eval.legalbench._call_ollama", return_value="Guilty mind"):
            report = run_eval(cfg)

        assert report["run_id"] == cfg.run_id
        assert report["subsets"][0]["subset"] == "definitions"
        assert report["subsets"][0]["n"] == 1
        # accuracy: stub returns "Guilty mind" which matches stub answer
        assert report["subsets"][0]["correct"] == 1

    def test_total_ollama_failure_is_an_infrastructure_error(
        self, tmp_path: Path
    ) -> None:
        """Spec 031: a dead Ollama must not report as accuracy 0.0."""
        from law_ai.eval.legalbench import (
            EvalInfrastructureError,
            LegalBenchConfig,
            run_eval,
        )

        cfg = LegalBenchConfig(
            subsets=["causation"],
            model="stub-model",
            limit=1,
            report_path=tmp_path / "run.json",
        )

        with (
            patch(
                "law_ai.eval.legalbench._call_ollama",
                side_effect=RuntimeError("Ollama offline"),
            ),
            pytest.raises(EvalInfrastructureError, match="infrastructure failure"),
        ):
            run_eval(cfg)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCLI:
    def test_parser_accepts_valid_args(self) -> None:
        from law_ai.eval.legalbench import _build_parser

        parser = _build_parser()
        args = parser.parse_args(
            ["--subset", "definitions", "--limit", "5", "--model", "phi3:mini"]
        )
        assert args.subset == "definitions"
        assert args.limit == 5
        assert args.model == "phi3:mini"


# ---------------------------------------------------------------------------
# Synthetic gate (BL-20260811-10) — a stub-backed run must never satisfy CI
# ---------------------------------------------------------------------------


class TestSyntheticGate:
    """`--fail-on-synthetic` is the flag that makes the nightly gate honest.

    Before the flip, a runner with no cached dataset scored five smoke
    fixtures, found no baseline to compare against, and exited 0 — a green
    gate that had measured nothing.
    """

    @staticmethod
    def _args(**overrides: bool) -> Any:
        from law_ai.eval.legalbench import _build_parser

        flags: list[str] = []
        if overrides.get("check_regression", True):
            flags.append("--check-regression")
        if overrides.get("fail_on_synthetic", True):
            flags.append("--fail-on-synthetic")
        if overrides.get("update_baseline", False):
            flags.append("--update-baseline")
        return _build_parser().parse_args(flags)

    def test_stub_backed_run_fails_the_gate(self, capsys: Any) -> None:
        from law_ai.eval.legalbench import _apply_gates

        report = {
            "synthetic": True,
            "subsets": [
                {"subset": "core_reasoning", "accuracy": 1.0, "synthetic": True}
            ],
        }
        assert _apply_gates(report, self._args()) == 1
        assert "synthetic" in capsys.readouterr().err

    def test_real_run_matching_its_baseline_passes(self) -> None:
        from law_ai.eval.legalbench import _apply_gates

        report = {
            "synthetic": False,
            "subsets": [
                {"subset": "core_reasoning", "accuracy": 0.62, "synthetic": False}
            ],
            "delta": {
                "core_reasoning": {"before": 0.62, "after": 0.62, "delta_pp": 0.0}
            },
        }
        assert _apply_gates(report, self._args()) == 0

    def test_real_run_regressing_more_than_a_point_fails(self) -> None:
        from law_ai.eval.legalbench import _apply_gates

        report = {
            "synthetic": False,
            "subsets": [
                {"subset": "core_reasoning", "accuracy": 0.60, "synthetic": False}
            ],
            "delta": {
                "core_reasoning": {"before": 0.62, "after": 0.60, "delta_pp": -2.0}
            },
        }
        assert _apply_gates(report, self._args()) == 1

    def test_ci_recipe_passes_the_flag(self) -> None:
        """The gate is only flipped if `make test-legalbench-gate` carries it."""
        makefile = Path("/repo/Makefile")
        if not makefile.exists():  # repo root not mounted in this container
            pytest.skip("/repo/Makefile not mounted")
        recipe = makefile.read_text(encoding="utf-8").split("test-legalbench-gate:")[1]
        assert "--fail-on-synthetic" in recipe.split("\n\n")[0]
