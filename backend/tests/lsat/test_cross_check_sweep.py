"""Tests for ``lsat_cross_check_sweep`` (BL-20260831-21).

The sweep is the only path that turns a blind-solve disagreement into a row a
reviewer will actually see, so these tests pin three things: the budget cap and
skip rules (every run bills provider calls), the queue semantics (a
disagreement becomes a ``crosscheck`` proposal, an agreement does not), and the
approve semantics (closing such a row must never write to the bank).
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError


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


def _verdict(choice: str) -> Any:
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=json.dumps({"choice": choice, "rationale": "Because."}),
        provider="claude_code",
        model="claude-opus-5",
        latency_ms=1.0,
    )


def _run(*args: str) -> str:
    out = StringIO()
    call_command("lsat_cross_check_sweep", *args, stdout=out)
    return out.getvalue()


def _lr_ids() -> list[str]:
    from law_ai.lsat.services.bank import load_bank

    return sorted(q.id for q in load_bank().values() if q.section == "LR")


def _keyed(choice_for: dict[str, str]) -> Any:
    """An agenerate stub answering per question id (from the prompt's stem)."""
    from law_ai.lsat.services.bank import load_bank

    stems = {q.stem: qid for qid, q in load_bank().items()}

    async def _agenerate(prompt: str, **kwargs: Any) -> Any:
        for stem, qid in stems.items():
            if stem in prompt:
                return _verdict(choice_for.get(qid, load_bank()[qid].correct))
        raise AssertionError("prompt matched no bank question")

    return _agenerate


class TestTargeting:
    def test_dry_run_lists_without_solving(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals

        mock = AsyncMock()
        with patch.object(cc_mod.llm, "agenerate", new=mock):
            output = _run("--section", "LR", "--limit", "2", "--dry-run")
        assert mock.await_count == 0
        assert output.count("would solve:") == 2
        assert proposals.list_proposals("pending") == []

    def test_limit_caps_provider_calls(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod

        with patch.object(cc_mod.llm, "agenerate", new=_keyed({})):
            output = _run("--section", "LR", "--limit", "2")
        assert output.count("agrees") == 2

    def test_section_filter_and_bad_section(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod

        with patch.object(cc_mod.llm, "agenerate", new=_keyed({})):
            output = _run("--section", "RC", "--limit", "1")
        assert "in RC" in output
        with pytest.raises(CommandError):
            _run("--section", "XX")
        with pytest.raises(CommandError):
            _run("--limit", "0")

    def test_already_checked_questions_are_skipped(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod

        first = _lr_ids()[0]
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({})):
            _run("--section", "LR", "--limit", "1")
            second = _run("--section", "LR", "--limit", "1")
        assert first not in second
        # ...unless the operator explicitly re-solves.
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({})):
            refreshed = _run("--section", "LR", "--limit", "1", "--refresh")
        assert first in refreshed


class TestQueueing:
    def test_disagreement_becomes_a_pending_crosscheck_proposal(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.bank import load_bank

        qid = _lr_ids()[0]
        wrong = "A" if load_bank()[qid].correct != "A" else "B"
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({qid: wrong})):
            output = _run("--section", "LR", "--limit", "1")
        assert "DISAGREES" in output

        rows = proposals.list_proposals("pending")
        assert [r["proposal_kind"] for r in rows] == ["crosscheck"]
        draft = rows[0]["draft"]
        assert draft["question_id"] == qid
        assert draft["bank_choice"] == load_bank()[qid].correct
        assert draft["model_choice"] == wrong

    def test_agreement_queues_nothing(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals

        with patch.object(cc_mod.llm, "agenerate", new=_keyed({})):
            _run("--section", "LR", "--limit", "2")
        assert proposals.list_proposals("pending") == []

    def test_degraded_verdicts_are_never_filed(self) -> None:
        """A provider outage is not a disagreement."""
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals

        async def boom(*args: Any, **kwargs: Any) -> Any:
            raise cc_mod.llm.LLMUnavailableError("chain down")

        with patch.object(cc_mod.llm, "agenerate", new=boom):
            output = _run("--section", "LR", "--limit", "2")
        assert "degraded" in output
        assert proposals.list_proposals("pending") == []

    def test_a_question_is_not_queued_twice(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.bank import load_bank

        qid = _lr_ids()[0]
        wrong = "A" if load_bank()[qid].correct != "A" else "B"
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({qid: wrong})):
            _run("--section", "LR", "--limit", "1")
            _run("--section", "LR", "--limit", "1", "--refresh")
        rows = [
            r
            for r in proposals.list_proposals("pending")
            if r["proposal_kind"] == "crosscheck"
        ]
        assert len(rows) == 1

    def test_validation_report_names_the_queued_review(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.bank import load_bank
        from law_ai.lsat.services.validation import validate_question_set

        qid = _lr_ids()[0]
        wrong = "A" if load_bank()[qid].correct != "A" else "B"
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({qid: wrong})):
            _run("--section", "LR", "--limit", "1")
        pid = proposals.list_proposals("pending")[0]["id"]

        summary = validate_question_set()["cross_checks"]
        row = next(d for d in summary["disagreements"] if d["question_id"] == qid)
        assert row["review_proposal_id"] == pid
        assert summary["queued_reviews"] == 1


class TestApproveSemantics:
    def test_approving_a_crosscheck_row_writes_nothing_to_the_bank(self) -> None:
        from law_ai.lsat.services import crosscheck as cc_mod
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.bank import load_bank

        qid = _lr_ids()[0]
        wrong = "A" if load_bank()[qid].correct != "A" else "B"
        with patch.object(cc_mod.llm, "agenerate", new=_keyed({qid: wrong})):
            _run("--section", "LR", "--limit", "1")
        pid = proposals.list_proposals("pending")[0]["id"]

        before = dict(load_bank())
        row = proposals.promote_crosscheck(pid, reviewer="alice", note="key verified")
        assert row["status"] == "approved"
        assert row["reviewer"] == "alice"
        after = load_bank()
        assert set(after) == set(before)
        assert after[qid].correct == before[qid].correct

    def test_promote_to_bank_refuses_a_crosscheck_row(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            {"question_id": "lr-001", "bank_choice": "A", "model_choice": "B"},
            agent_trace_id="",
            model="m",
            confidence=0.0,
            proposal_kind="crosscheck",
        )
        with pytest.raises(ValueError, match="crosscheck"):
            proposals.promote_to_bank(pid)
        with pytest.raises(ValueError, match="crosscheck"):
            proposals.promote_guide_to_bank(pid)

    def test_promote_crosscheck_refuses_other_kinds_and_closed_rows(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            {"question_id": "lr-001", "bank_choice": "A", "model_choice": "B"},
            agent_trace_id="",
            model="m",
            confidence=0.0,
            proposal_kind="crosscheck",
        )
        proposals.promote_crosscheck(pid, reviewer="alice")
        with pytest.raises(ValueError, match="cannot be closed"):
            proposals.promote_crosscheck(pid, reviewer="alice")
        with pytest.raises(KeyError):
            proposals.promote_crosscheck("prop-missing")
