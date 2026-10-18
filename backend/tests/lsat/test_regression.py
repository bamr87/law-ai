"""Per-item cross-check regression tracking (BL-20260527-06)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )
    monkeypatch.setattr(
        settings,
        "LSAT_RESPONSE_CACHE_DIR",
        str(tmp_path / "response_cache"),
        raising=False,
    )
    from law_ai.lsat.services import bank as bank_mod

    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
        "guides.json",
    ):
        src = real / name
        if src.is_file():
            (sandbox / name).write_text(src.read_text(encoding="utf-8"))
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
    bank_mod.reset_caches()
    yield
    bank_mod.reset_caches()


@cache
def _days_ago(n: int) -> str:
    """An ISO timestamp *n* days back, stable within a run.

    Relative rather than fixed because the report now drops verdicts older
    than ``DEFAULT_SINCE_DAYS`` (BL-20260905-59): a literal date would quietly
    age out of the window and take these tests with it. Cached so that two
    calls with the same *n* produce the same string — the de-duplication test
    depends on a JSONL event and a DB row sharing a timestamp exactly.
    """
    return (datetime.now(UTC) - timedelta(days=n)).isoformat()


def _seed(
    qid: str,
    *,
    agree: bool | None,
    ts: str,
    used_llm: bool = True,
    cached: bool = False,
    model: str = "claude_code/claude-opus-5",
) -> None:
    from law_ai.core import audit_jsonl as audit_store

    audit_store.record(
        {
            "type": "lsat_cross_check",
            "timestamp": ts,
            "prompt_version": "lsat-cross-check/1",
            "question_id": qid,
            "bank_choice": "A",
            "model_choice": "A" if agree else "B",
            "agree": agree,
            "model": model,
            "used_llm": used_llm,
            "cached": cached,
            "requires_human_review": agree is False,
        }
    )


def _qids(section: str) -> list[str]:
    from law_ai.lsat.services.bank import load_bank

    return sorted(q.id for q in load_bank().values() if q.section == section)


class TestRegressionReport:
    def test_empty_history_is_empty_report(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        report = regression_report()
        assert report["tracked"] == 0
        assert report["regressed"] == []
        assert report["recovered"] == []

    def test_agree_then_disagree_is_a_regression(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(5))
        _seed(qid, agree=False, ts=_days_ago(3), model="grok-4")
        report = regression_report()
        assert report["tracked"] == 1
        assert report["recovered"] == []
        (row,) = report["regressed"]
        assert row["question_id"] == qid
        assert row["verdicts"] == 2
        assert row["first"]["agree"] is True
        assert row["latest"]["agree"] is False
        assert row["latest"]["model"] == "grok-4"

    def test_disagree_then_agree_is_a_recovery(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        qid = _qids("LR")[0]
        _seed(qid, agree=False, ts=_days_ago(5))
        _seed(qid, agree=True, ts=_days_ago(4))
        report = regression_report()
        assert report["regressed"] == []
        assert [r["question_id"] for r in report["recovered"]] == [qid]

    def test_stable_verdicts_are_tracked_but_not_flagged(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(5))
        _seed(qid, agree=True, ts=_days_ago(4))
        report = regression_report()
        assert report["tracked"] == 1
        assert report["regressed"] == [] and report["recovered"] == []

    def test_cached_and_degraded_verdicts_are_ignored(self) -> None:
        """Only fresh solves are observations; cache re-reads and outages are not."""
        from law_ai.lsat.services.regression import cross_check_history

        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(5))
        _seed(qid, agree=True, ts=_days_ago(4), cached=True)
        _seed(
            qid,
            agree=None,
            ts=_days_ago(3),
            used_llm=False,
            model="fallback/offline",
        )
        history = cross_check_history()
        assert [v["timestamp"] for v in history[qid]] == [_days_ago(5)]

    def test_history_is_sorted_oldest_first_regardless_of_log_order(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        qid = _qids("LR")[0]
        # Written out of order (e.g. a Celery-persisted row landing late).
        _seed(qid, agree=False, ts=_days_ago(1))
        _seed(qid, agree=True, ts=_days_ago(5))
        report = regression_report()
        assert [r["question_id"] for r in report["regressed"]] == [qid]

    def test_an_old_first_verdict_ages_out_of_the_comparison(self) -> None:
        """BL-20260905-59 — months-old verdicts are not today's baseline.

        A verdict from before the window was produced by a different model and
        prompt version, so a disagreement with it is not evidence that the
        item regressed.
        """
        from law_ai.lsat.services.regression import (
            DEFAULT_SINCE_DAYS,
            regression_report,
        )

        assert DEFAULT_SINCE_DAYS is not None
        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(DEFAULT_SINCE_DAYS + 30))
        _seed(qid, agree=False, ts=_days_ago(1))

        report = regression_report()
        assert report["since_days"] == DEFAULT_SINCE_DAYS
        assert report["regressed"] == [], "the stale verdict must not anchor a flip"
        assert report["tracked"] == 1  # the recent verdict is still tracked

        # The whole history is still available on request.
        all_time = regression_report(since_days=None)
        assert [r["question_id"] for r in all_time["regressed"]] == [qid]
        assert all_time["since_days"] is None

    def test_a_verdict_inside_the_window_still_flips(self) -> None:
        from law_ai.lsat.services.regression import (
            DEFAULT_SINCE_DAYS,
            regression_report,
        )

        assert DEFAULT_SINCE_DAYS is not None
        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(DEFAULT_SINCE_DAYS - 1))
        _seed(qid, agree=False, ts=_days_ago(1))
        assert [r["question_id"] for r in regression_report()["regressed"]] == [qid]

    def test_section_filter(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        lr, rc = _qids("LR")[0], _qids("RC")[0]
        for qid in (lr, rc):
            _seed(qid, agree=True, ts=_days_ago(5))
            _seed(qid, agree=False, ts=_days_ago(4))
        assert {r["question_id"] for r in regression_report()["regressed"]} == {lr, rc}
        only_rc = regression_report(section="RC")
        assert [r["question_id"] for r in only_rc["regressed"]] == [rc]
        assert only_rc["tracked"] == 1

    def test_unknown_question_ids_are_skipped(self) -> None:
        from law_ai.lsat.services.regression import regression_report

        _seed("nope-999", agree=True, ts=_days_ago(5))
        _seed("nope-999", agree=False, ts=_days_ago(4))
        assert regression_report()["tracked"] == 0

    def test_db_rows_and_jsonl_rows_are_deduplicated(self) -> None:
        """The same event lands in both stores; it must count once."""
        from law_ai.audit.models import AuditEvent
        from law_ai.lsat.services.regression import cross_check_history

        qid = _qids("LR")[0]
        _seed(qid, agree=True, ts=_days_ago(5))
        AuditEvent.objects.create(
            kind="lsat_cross_check",
            payload={
                "type": "lsat_cross_check",
                "timestamp": _days_ago(5),
                "question_id": qid,
                "agree": True,
                "used_llm": True,
                "cached": False,
                "model": "m",
            },
        )
        # A DB-only, later verdict (JSONL ring rotated past it, say).
        AuditEvent.objects.create(
            kind="lsat_cross_check",
            payload={
                "type": "lsat_cross_check",
                "timestamp": _days_ago(4),
                "question_id": qid,
                "agree": False,
                "used_llm": True,
                "cached": False,
                "model": "m",
            },
        )
        history = cross_check_history()
        assert [v["agree"] for v in history[qid]] == [True, False]


def _verdict(choice: str) -> Any:
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=json.dumps({"choice": choice, "rationale": "Because."}),
        provider="claude_code",
        model="claude-opus-5-5",
        latency_ms=1.0,
    )


def _draft(section: str = "LR") -> dict[str, Any]:
    return {
        "section": section,
        "difficulty": "med",
        "stem": "Regression stem.",
        "choices": [{"label": lab, "text": lab.lower()} for lab in "ABCDE"],
        "correct": "C",
        "explanation": "Because C.",
        "concepts": ["parallel-reasoning"],
        "confidence": 0.8,
    }


class TestCrossCheckOnApproval:
    def test_fresh_verdict_is_pinned_to_the_proposal_and_audited(self) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.regression import cross_check_history

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t", model="m", confidence=0.8
        )
        row = proposals.promote_to_bank(pid, reviewer="alice")
        with patch.object(
            cc_mod.llm, "agenerate", new=AsyncMock(return_value=_verdict("C"))
        ):
            verdict = proposals.cross_check_on_approval(pid)
        assert verdict is not None
        assert verdict["question_id"] == row["question_id"]
        assert verdict["agree"] is True
        assert verdict["used_llm"] is True
        assert verdict["model_choice"] == "C"

        replayed = proposals.get_proposal(pid)
        assert replayed is not None
        assert replayed["cross_check"]["agree"] is True
        assert replayed["status"] == "approved"

        events = [
            e for e in audit_store.tail(50) if e.get("type") == "lsat_cross_check"
        ]
        assert len(events) == 1 and events[0]["cached"] is False
        assert row["question_id"] in cross_check_history()

    def test_disagreement_is_recorded_not_rejected(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t", model="m", confidence=0.8
        )
        proposals.promote_to_bank(pid, reviewer="alice")
        with patch.object(
            cc_mod.llm, "agenerate", new=AsyncMock(return_value=_verdict("A"))
        ):
            verdict = proposals.cross_check_on_approval(pid)
        assert verdict is not None
        assert verdict["agree"] is False
        assert verdict["requires_human_review"] is True
        row = proposals.get_proposal(pid)
        assert row is not None and row["status"] == "approved"

    def test_provider_outage_never_undoes_the_approval(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t", model="m", confidence=0.8
        )
        proposals.promote_to_bank(pid, reviewer="alice")

        async def boom(*args: object, **kwargs: object) -> object:
            raise cc_mod.llm.LLMUnavailableError("down")

        with patch.object(cc_mod.llm, "agenerate", new=boom):
            verdict = proposals.cross_check_on_approval(pid)
        assert verdict is not None
        assert verdict["used_llm"] is False
        assert verdict["agree"] is None
        row = proposals.get_proposal(pid)
        assert row is not None and row["status"] == "approved"

    def test_non_question_or_pending_rows_are_skipped(self) -> None:
        from law_ai.lsat.services import proposals

        pending = proposals.record_proposal(
            _draft(), agent_trace_id="t", model="m", confidence=0.8
        )
        assert proposals.cross_check_on_approval(pending) is None
        assert proposals.cross_check_on_approval("prop-missing") is None

    def test_later_sweep_detects_a_flip_against_the_approval_baseline(self) -> None:
        """End to end: approve (agree) -> later blind solve (disagree) -> flagged."""
        from asgiref.sync import async_to_sync

        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.bank import load_bank
        from law_ai.lsat.services.regression import regression_report
        from law_ai.lsat.services.validation import validate_question_set

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t", model="m", confidence=0.8
        )
        row = proposals.promote_to_bank(pid, reviewer="alice")
        with patch.object(
            cc_mod.llm, "agenerate", new=AsyncMock(return_value=_verdict("C"))
        ):
            proposals.cross_check_on_approval(pid)
        q = load_bank()[row["question_id"]]
        with patch.object(
            cc_mod.llm, "agenerate", new=AsyncMock(return_value=_verdict("D"))
        ):
            async_to_sync(cc_mod.cross_check)(q, refresh=True)

        report = regression_report()
        assert [r["question_id"] for r in report["regressed"]] == [q.id]
        payload = validate_question_set()
        assert payload["regressions"]["regressed"][0]["question_id"] == q.id
        assert payload["regressions"]["tracked"] == 1
