"""Tests for the LSAT proposals service + API (spec 019 T-002, T-003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point both audit + proposal stores at the test tmp dir."""
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )

    # Each test gets its own copy of the bank so promote_to_bank does not
    # mutate the checked-in fixture data.
    from law_ai.lsat.services import bank as bank_mod

    real_data_dir = bank_mod.DATA_DIR
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
        src = real_data_dir / name
        if src.is_file():
            (sandbox / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    from law_ai.lsat.services import guides as guides_mod

    def _clear() -> None:
        bank_mod.load_bank.cache_clear()
        bank_mod.load_concepts.cache_clear()
        bank_mod.load_passages.cache_clear()
        bank_mod.load_sections.cache_clear()
        guides_mod.reset_guide_cache()

    _clear()
    yield
    _clear()


def _draft(section: str = "LR") -> dict[str, Any]:
    return {
        "section": section,
        "difficulty": "med",
        "stem": "Sample stem.",
        "choices": [
            {"label": "A", "text": "alpha"},
            {"label": "B", "text": "bravo"},
            {"label": "C", "text": "charlie"},
            {"label": "D", "text": "delta"},
            {"label": "E", "text": "echo"},
        ],
        "correct": "A",
        "explanation": "Because.",
        "concepts": ["parallel-reasoning"],
        "confidence": 0.8,
    }


class TestStoreRoundTrip:
    def test_record_and_list_pending(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.8
        )
        rows = proposals.list_proposals("pending")
        assert len(rows) == 1
        assert rows[0]["id"] == pid
        assert rows[0]["status"] == "pending"

    def test_reject_sets_status(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.8
        )
        proposals.set_status(pid, "rejected", reviewer="alice", note="off-topic")
        assert proposals.list_proposals("pending") == []
        rejected = proposals.list_proposals("rejected")
        assert len(rejected) == 1
        assert rejected[0]["status"] == "rejected"
        assert rejected[0]["reviewer"] == "alice"

    def test_promote_to_bank_appends_and_invalidates_cache(self) -> None:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
        )
        before = len(bank_mod.load_bank())
        row = proposals.promote_to_bank(pid, reviewer="alice")
        after = bank_mod.load_bank()
        assert len(after) == before + 1
        assert row["status"] == "approved"
        assert row["question_id"] in after

    def test_double_promote_raises(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.9
        )
        proposals.promote_to_bank(pid, reviewer="a")
        with pytest.raises(ValueError):
            proposals.promote_to_bank(pid, reviewer="a")


class TestGapAnalysis:
    def test_empty_audit_yields_no_gaps(self) -> None:
        from law_ai.lsat.services import proposals

        assert proposals.gap_analysis() == []

    def test_ranks_lowest_accuracy_first(self) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.services import proposals

        # weak concept: 3 attempts, 0 correct (accuracy 0.0)
        for _ in range(3):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "section": "LR",
                    "concepts": ["weak"],
                    "correct": False,
                }
            )
        # strong concept: 3 attempts, 3 correct (accuracy 1.0)
        for _ in range(3):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "section": "LR",
                    "concepts": ["strong"],
                    "correct": True,
                }
            )
        gaps = proposals.gap_analysis()
        assert len(gaps) == 2
        assert gaps[0]["concept"] == "weak"
        assert gaps[0]["accuracy"] == 0.0
        assert gaps[1]["concept"] == "strong"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    from law_ai.asgi import application as app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_generate_persists_and_lists(client: AsyncClient) -> None:
    from law_ai.agents_runtime.crews import lsat_content_author as mod

    payload = json.dumps(
        {
            "drafts": [
                {
                    "section": "LR",
                    "difficulty": "med",
                    "stem": "Sample stem from LLM.",
                    "choices": [
                        {"label": label, "text": label}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                    "correct": "B",
                    "explanation": "Because B.",
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.75,
                }
            ]
        }
    )
    from law_ai.core.llm.base import LLMResult

    result = LLMResult(
        text=payload, provider="claude_code", model="claude-opus-5", latency_ms=1.0
    )
    with patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=result)):
        res = await client.post(
            "/api/lsat/proposals/generate",
            json={"section": "LR", "difficulty": "med", "count": 1},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 1
    pid = body["proposals"][0]["id"]

    listed = await client.get("/api/lsat/proposals", params={"status": "pending"})
    assert listed.status_code == 200
    assert listed.json()["proposals"][0]["id"] == pid


@pytest.mark.asyncio
async def test_approve_then_question_visible(client: AsyncClient) -> None:
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
    )
    res = await client.post(f"/api/lsat/proposals/{pid}/approve", json={})
    assert res.status_code == 200, res.text
    qid = res.json()["question_id"]

    fetched = await client.get(f"/api/lsat/questions/{qid}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == qid


@pytest.mark.asyncio
async def test_reject_marks_status(client: AsyncClient) -> None:
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.5
    )
    res = await client.post(f"/api/lsat/proposals/{pid}/reject", json={"note": "nope"})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_gaps_endpoint_returns_empty_initially(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/gaps")
    assert res.status_code == 200
    body = res.json()
    assert body["gaps"] == []
    assert "limit" in body


# ---------------------------------------------------------------------------
# Spec 041 — guide drafts in the proposal queue (T-004, AC-6)
# ---------------------------------------------------------------------------


def _guide_draft(question_id: str) -> dict[str, Any]:
    from law_ai.lsat.services.bank import load_bank

    bank = load_bank()
    correct = bank[question_id].correct if question_id in bank else "B"
    return {
        "question_id": question_id,
        "method": "test walkthrough",
        "steps": [
            {"kind": "orient", "title": "Read", "text": "Read the stem."},
            {"kind": "symbolize", "title": "Notate", "text": "Symbolize the rule."},
            {"kind": "infer", "title": "Chain", "text": "Chain the inference."},
            {
                "kind": "answer",
                "title": "Answer",
                "text": f"Pick {correct}.",
                "spoiler": True,
            },
        ],
    }


class TestGuideProposals:
    def _guideless_qid(self) -> str:
        from law_ai.lsat.services.bank import load_bank
        from law_ai.lsat.services.guides import load_guides

        guides = load_guides()
        return next(q for q in load_bank() if q not in guides)

    def test_record_and_replay_carries_kind(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _guide_draft(self._guideless_qid()),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        row = proposals.get_proposal(pid)
        assert row is not None and row["proposal_kind"] == "guide"

        # Legacy question drafts backfill as kind "question".
        qpid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t-q", model="m", confidence=0.7
        )
        qrow = proposals.get_proposal(qpid)
        assert qrow is not None and qrow["proposal_kind"] == "question"

    def test_question_promotion_rejects_guide_drafts(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _guide_draft(self._guideless_qid()),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        with pytest.raises(ValueError, match="promote_guide_to_bank"):
            proposals.promote_to_bank(pid)

    def test_guide_promotion_rejects_question_drafts(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t-q", model="m", confidence=0.7
        )
        with pytest.raises(ValueError, match="promote_to_bank"):
            proposals.promote_guide_to_bank(pid)

    def test_promote_guide_serves_via_loader(self) -> None:
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.guides import load_guides

        qid = self._guideless_qid()
        pid = proposals.record_proposal(
            _guide_draft(qid),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        row = proposals.promote_guide_to_bank(pid, reviewer="rev", note="ok")
        assert row["status"] == "approved"
        assert row["question_id"] == qid

        guides = load_guides()
        assert qid in guides
        assert guides[qid].source.startswith("LSATSolveGuideAuthor (approved")

    def test_promote_guide_rejects_duplicate_question(self) -> None:
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.guides import load_guides

        existing_qid = next(iter(load_guides()))
        pid = proposals.record_proposal(
            _guide_draft(existing_qid),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        with pytest.raises(ValueError, match="already has a solve guide"):
            proposals.promote_guide_to_bank(pid)

    def test_promote_guide_rejects_invalid_draft(self) -> None:
        from law_ai.lsat.services import proposals

        bad = _guide_draft(self._guideless_qid())
        bad["steps"] = []
        pid = proposals.record_proposal(
            bad,
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            proposals.promote_guide_to_bank(pid)
