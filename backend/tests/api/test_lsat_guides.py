"""Tests for /api/lsat guide endpoints (spec 041 AC-2, AC-3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings
from law_ai.core import audit_jsonl as audit_store
from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.guides import load_guides
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _guided_question_id() -> str:
    return next(iter(load_guides()))


def _guideless_question_id() -> str:
    guides = load_guides()
    return next(qid for qid in load_bank() if qid not in guides)


# ---------------------------------------------------------------------------
# AC-2 — guide endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guide_withholds_spoiler_steps_by_default(client: AsyncClient) -> None:
    qid = _guided_question_id()
    res = await client.get(f"/api/lsat/questions/{qid}/guide")
    assert res.status_code == 200
    body = res.json()
    assert body["question_id"] == qid
    assert body["step_count"] == len(body["steps"])
    locked = [s for s in body["steps"] if s.get("locked")]
    assert locked, "seed guides all carry at least one spoiler step"
    for step in locked:
        assert step["spoiler"] is True
        assert "text" not in step
        assert "representation" not in step
    unlocked = [s for s in body["steps"] if not s.get("locked")]
    assert unlocked and all(s["text"] for s in unlocked)


@pytest.mark.asyncio
async def test_guide_spoilers_param_returns_full_steps(client: AsyncClient) -> None:
    qid = _guided_question_id()
    res = await client.get(f"/api/lsat/questions/{qid}/guide", params={"spoilers": "1"})
    assert res.status_code == 200
    body = res.json()
    assert all(s["locked"] is False for s in body["steps"])
    assert all(s["text"] for s in body["steps"])


@pytest.mark.asyncio
async def test_guide_unknown_question_404_without_tutor(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/questions/nope/guide")
    assert res.status_code == 404
    assert res.json()["has_tutor"] is False


@pytest.mark.asyncio
async def test_guide_less_question_404_offers_tutor(client: AsyncClient) -> None:
    qid = _guideless_question_id()
    res = await client.get(f"/api/lsat/questions/{qid}/guide")
    assert res.status_code == 404
    assert res.json()["has_tutor"] is True


@pytest.mark.asyncio
async def test_guide_fetch_emits_audit_event(client: AsyncClient) -> None:
    qid = _guided_question_id()
    res = await client.get(f"/api/lsat/questions/{qid}/guide")
    assert res.status_code == 200
    events = [e for e in audit_store.tail(50) if e.get("type") == "lsat_guide"]
    assert len(events) == 1
    ev = events[0]
    assert ev["question_id"] == qid
    assert ev["spoilers"] is False
    assert ev["step_count"] >= 4


# ---------------------------------------------------------------------------
# AC-3 — hint-aware grading + stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grade_records_hints_used_and_stats_split(client: AsyncClient) -> None:
    bank = load_bank()
    items = list(bank.values())
    q1, q2 = items[0], items[1]
    res = await client.post(
        "/api/lsat/grade",
        json={"question_id": q1.id, "choice": q1.correct, "hints_used": 3},
    )
    assert res.status_code == 200
    res = await client.post(
        "/api/lsat/grade", json={"question_id": q2.id, "choice": q2.correct}
    )
    assert res.status_code == 200

    grade_events = [e for e in audit_store.tail(50) if e.get("type") == "lsat_grade"]
    hints = [e.get("hints_used") for e in grade_events]
    assert len(hints) == 2 and 3 in hints and None in hints

    stats = (await client.get("/api/lsat/stats")).json()
    assert stats["attempts"] == 2
    assert stats["assisted"] == 1
    assert stats["unassisted"] == 1
    assisted_by_section = {sec: b["assisted"] for sec, b in stats["by_section"].items()}
    assert sum(assisted_by_section.values()) == 1
    for bucket in stats["by_section"].values():
        assert bucket["attempts"] == bucket["assisted"] + bucket["unassisted"]


@pytest.mark.asyncio
async def test_grade_rejects_out_of_bounds_hints(client: AsyncClient) -> None:
    bank = load_bank()
    qid, q = next(iter(bank.items()))
    for bad in (-1, 21):
        res = await client.post(
            "/api/lsat/grade",
            json={"question_id": qid, "choice": q.correct, "hints_used": bad},
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# AC-6 — guide drafting stays HITL-gated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_guide_persists_pending_and_never_serves(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json
    from unittest.mock import AsyncMock, patch

    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod
    from law_ai.core.llm.base import LLMResult

    qid = _guideless_question_id()
    correct = load_bank()[qid].correct
    payload = _json.dumps(
        {
            "guide": {
                "question_id": qid,
                "method": "Symbolize then eliminate",
                "steps": [
                    {"kind": "orient", "title": "Read", "text": "Read the stem."},
                    {"kind": "symbolize", "title": "Notate", "text": "Arrows."},
                    {"kind": "infer", "title": "Chain", "text": "Apply."},
                    {
                        "kind": "answer",
                        "title": "Answer",
                        "text": f"It is {correct}.",
                        "spoiler": True,
                    },
                ],
            }
        }
    )
    result = LLMResult(
        text=payload, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
    )
    with patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=result)):
        res = await client.post("/api/lsat/guides/generate", json={"question_id": qid})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["degraded"] is False
    assert body["proposal"]["proposal_kind"] == "guide"
    assert body["proposal"]["status"] == "pending"

    # The pending draft must NOT serve on the guide endpoint (NFR-HITL-1).
    res = await client.get(f"/api/lsat/questions/{qid}/guide")
    assert res.status_code == 404

    listed = await client.get("/api/lsat/proposals", params={"status": "pending"})
    kinds = [p["proposal_kind"] for p in listed.json()["proposals"]]
    assert "guide" in kinds


@pytest.mark.asyncio
async def test_generate_guide_unknown_question_404(client: AsyncClient) -> None:
    res = await client.post("/api/lsat/guides/generate", json={"question_id": "nope"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_generate_guide_conflict_when_guide_exists(client: AsyncClient) -> None:
    qid = _guided_question_id()
    res = await client.post("/api/lsat/guides/generate", json={"question_id": qid})
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# BL-20260830-15 — the judge-tier verdict rides with the pending draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_guide_attaches_the_reviewer_verdict(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json
    from unittest.mock import AsyncMock, patch

    from law_ai.agents_runtime.crews import lsat_guide_reviewer as reviewer_mod
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod
    from law_ai.core.llm.base import LLMResult

    qid = _guideless_question_id()
    correct = load_bank()[qid].correct
    guide_payload = _json.dumps(
        {
            "guide": {
                "question_id": qid,
                "method": "Symbolize then eliminate",
                "steps": [
                    {"kind": "orient", "title": "Read", "text": "Read the stem."},
                    {
                        "kind": "answer",
                        "title": "Answer",
                        "text": f"It is {correct}.",
                        "spoiler": True,
                    },
                ],
            }
        }
    )
    review_payload = _json.dumps(
        {
            "verdict": "revise",
            "symbolization_faithful": False,
            "step_findings": [
                {"index": 1, "follows": True, "note": ""},
                {"index": 2, "follows": False, "note": "the chain never reaches it"},
            ],
            "summary": "Step 2 asserts more than step 1 licenses.",
            "confidence": 0.7,
        }
    )

    def _result(text: str) -> LLMResult:
        return LLMResult(
            text=text, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
        )

    # The author and the reviewer share `law_ai.core.llm`, so the reviewer is
    # stubbed at its own entry point rather than through the shared module.
    # A plain async def (not AsyncMock) because the view calls it through
    # `async_to_sync`, which wants a real coroutine function.
    async def fake_review(guide, *, question=None):  # type: ignore[no-untyped-def]
        return _json.loads(review_payload)

    with (
        patch.object(
            mod.llm, "agenerate", new=AsyncMock(return_value=_result(guide_payload))
        ),
        patch.object(reviewer_mod, "review_guide", new=fake_review),
    ):
        res = await client.post("/api/lsat/guides/generate", json={"question_id": qid})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review"]["verdict"] == "revise"
    # The verdict is persisted on the pending row, not just echoed.
    review = body["proposal"]["meta"]["review"]
    assert review["symbolization_faithful"] is False
    assert review["step_findings"][1]["follows"] is False
    # Advisory only: the draft is still pending and still not served.
    assert body["proposal"]["status"] == "pending"
    served = await client.get(f"/api/lsat/questions/{qid}/guide")
    assert served.status_code == 404
