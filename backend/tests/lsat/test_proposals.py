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
    ):
        src = real_data_dir / name
        if src.is_file():
            (sandbox / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
    bank_mod.load_bank.cache_clear()
    bank_mod.load_concepts.cache_clear()
    bank_mod.load_passages.cache_clear()
    bank_mod.load_sections.cache_clear()
    yield
    bank_mod.load_bank.cache_clear()
    bank_mod.load_concepts.cache_clear()
    bank_mod.load_passages.cache_clear()
    bank_mod.load_sections.cache_clear()


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
    with patch.object(mod, "_ollama_generate", new=AsyncMock(return_value=payload)):
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
