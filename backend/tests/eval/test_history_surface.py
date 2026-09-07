"""Surfacing the LegalBench score history (BL-20260811-12).

The history was written to `backend/var/legalbench/history.jsonl` and read by
exactly one consumer: a CI upload-artifact step. Meanwhile the autonomy digest
had rendered a "LegalBench Delta" section since spec 018 that nothing ever
emitted an event for, so it printed `*(none)*` forever.

These tests pin both halves of the fix: the per-subset audit event the harness
now emits (the durable route, read by `compose_digest`), and the Markdown
summary nightly writes into the run page.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from law_ai.eval.legalbench import LegalBenchConfig
from law_ai.eval.report import write_report

_SUMMARY_SCRIPT = Path("/repo/scripts/legalbench_summary.py")


@pytest.fixture()
def isolated_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep history/baseline writes out of the real cache directory."""
    import law_ai.eval.report as report_module

    monkeypatch.setattr(report_module, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(report_module, "BASELINE_PATH", tmp_path / "baseline.json")
    return tmp_path


def _rows() -> list[dict[str, Any]]:
    return [
        {
            "subset": "core_reasoning",
            "n": 4,
            "scored": 4,
            "errored": 0,
            "correct": 3,
            "accuracy": 0.75,
            "scorer": "default_match",
            "synthetic": False,
            "items": [],
        },
        {
            "subset": "precedent_retrieval",
            "n": 2,
            "scored": 2,
            "errored": 0,
            "correct": 1,
            "accuracy": 0.5,
            "scorer": "bm25_recall@1",
            "synthetic": True,
            "items": [],
        },
    ]


class TestDeltaEvents:
    def test_one_event_per_subset_reaches_provenance(
        self, isolated_artifacts: Path
    ) -> None:
        config = LegalBenchConfig(
            subsets=["core_reasoning", "precedent_retrieval"],
            model="stub-model",
            report_path=isolated_artifacts / "run.json",
        )
        with patch("law_ai.core.provenance._persist") as persist:
            write_report(_rows(), config=config)

        events = [call.args[0] for call in persist.call_args_list]
        assert [event["type"] for event in events] == [
            "autonomy_legalbench_delta",
            "autonomy_legalbench_delta",
        ]
        assert [event["task"] for event in events] == [
            "core_reasoning",
            "precedent_retrieval",
        ]

    def test_event_payload_matches_what_the_digest_reads(
        self, isolated_artifacts: Path
    ) -> None:
        """`compose_digest` renders `payload['task']` and `payload['delta']`."""
        (isolated_artifacts / "baseline.json").write_text(
            json.dumps({"accuracies": {"core_reasoning": 0.70}}), encoding="utf-8"
        )
        config = LegalBenchConfig(
            subsets=["core_reasoning"],
            model="stub-model",
            report_path=isolated_artifacts / "run.json",
        )
        with patch("law_ai.core.provenance._persist") as persist:
            write_report(_rows()[:1], config=config)

        event = persist.call_args_list[0].args[0]
        assert event["task"] == "core_reasoning"
        assert event["delta"] == pytest.approx(5.0)  # 0.70 -> 0.75 == +5 pp
        assert event["baseline"] == pytest.approx(0.70)
        assert event["accuracy"] == pytest.approx(0.75)
        assert event["scorer"] == "default_match"
        assert event["synthetic"] is False
        assert event["source"] == "legalbench"

    def test_stub_backed_rows_are_flagged_in_the_event(
        self, isolated_artifacts: Path
    ) -> None:
        config = LegalBenchConfig(
            subsets=["precedent_retrieval"],
            model="stub-model",
            report_path=isolated_artifacts / "run.json",
        )
        with patch("law_ai.core.provenance._persist") as persist:
            write_report(_rows()[1:], config=config)

        event = persist.call_args_list[0].args[0]
        assert event["synthetic"] is True
        assert event["confidence"] == 0.0

    def test_audit_failure_never_breaks_the_run(self, isolated_artifacts: Path) -> None:
        config = LegalBenchConfig(
            subsets=["core_reasoning"],
            model="stub-model",
            report_path=isolated_artifacts / "run.json",
        )
        with patch(
            "law_ai.core.provenance._persist", side_effect=RuntimeError("audit down")
        ):
            report = write_report(_rows()[:1], config=config)
        assert report["subsets"][0]["accuracy"] == 0.75

    def test_history_row_records_the_scorer(self, isolated_artifacts: Path) -> None:
        config = LegalBenchConfig(
            subsets=["core_reasoning", "precedent_retrieval"],
            model="stub-model",
            report_path=isolated_artifacts / "run.json",
        )
        with patch("law_ai.core.provenance._persist"):
            write_report(_rows(), config=config)

        row = json.loads(
            (isolated_artifacts / "history.jsonl").read_text().splitlines()[-1]
        )
        assert row["scorer"] == {
            "core_reasoning": "default_match",
            "precedent_retrieval": "bm25_recall@1",
        }


def _load_summary_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("legalbench_summary", _SUMMARY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(
    not _SUMMARY_SCRIPT.exists(), reason="repo root not mounted at /repo"
)
class TestStepSummary:
    def test_renders_a_table_of_recent_runs(self, tmp_path: Path) -> None:
        module = _load_summary_script()
        history = tmp_path / "history.jsonl"
        history.write_text(
            json.dumps(
                {
                    "timestamp": "2026-09-05T00:00:00Z",
                    "model": "mistral:7b-instruct-q4_K_M",
                    "accuracies": {"core_reasoning": 0.75},
                    "scorer": {"core_reasoning": "default_match"},
                    "synthetic": {"core_reasoning": False},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        out = module.render(module.load_rows(history, 10))
        assert "## LegalBench score history" in out
        assert "0.7500" in out
        assert "mistral:7b-instruct-q4_K_M" in out
        assert "| no |" in out

    def test_flags_stub_backed_runs(self, tmp_path: Path) -> None:
        module = _load_summary_script()
        history = tmp_path / "history.jsonl"
        history.write_text(
            json.dumps(
                {
                    "timestamp": "2026-09-05T00:00:00Z",
                    "model": "stub-model",
                    "accuracies": {"core_reasoning": 1.0},
                    "synthetic": {"core_reasoning": True},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        assert "**yes**" in module.render(module.load_rows(history, 10))

    def test_missing_history_is_not_an_error(self, tmp_path: Path) -> None:
        module = _load_summary_script()
        out = module.render(module.load_rows(tmp_path / "nope.jsonl", 10))
        assert "No runs recorded" in out

    def test_malformed_lines_are_skipped(self, tmp_path: Path) -> None:
        module = _load_summary_script()
        history = tmp_path / "history.jsonl"
        history.write_text('{"broken": \n{"model": "m"}\n', encoding="utf-8")
        assert len(module.load_rows(history, 10)) == 1
