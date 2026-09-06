"""Tests for walkthrough caching, cross-check, and validation (spec 041 FR-13..15)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings
from law_ai.core import audit_jsonl as audit_store
from law_ai.lsat.services.bank import load_bank
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings,
        "LSAT_RESPONSE_CACHE_DIR",
        str(tmp_path / "response_cache"),
        raising=False,
    )


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _llm_result(text: str):
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-opus-5", latency_ms=1.0
    )


def _tutor_payload() -> str:
    return json.dumps(
        {
            "coaching": "Walkthrough: symbolize the rule, then chain it.",
            "next_steps": ["Diagram the conditionals"],
        }
    )


# ---------------------------------------------------------------------------
# FR-13 — walkthrough caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tutor_walkthrough_served_from_cache_on_repeat(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services import tutor as tutor_mod

    qid = next(iter(load_bank()))
    mock = AsyncMock(return_value=_llm_result(_tutor_payload()))
    body = {"question_id": qid, "user_question": "Walk me through the setup."}

    with patch.object(tutor_mod.llm, "agenerate", new=mock):
        first = (await client.post("/api/lsat/tutor", json=body)).json()
        second = (await client.post("/api/lsat/tutor", json=body)).json()

    assert mock.await_count == 1, "second identical request must not call the LLM"
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["coaching"] == first["coaching"]
    assert second["model"] == first["model"]

    events = [e for e in audit_store.tail(20) if e.get("type") == "lsat_tutor"]
    assert sorted(e["cached"] for e in events) == [False, True]


@pytest.mark.asyncio
async def test_tutor_refresh_bypasses_cache(client: AsyncClient) -> None:
    from law_ai.lsat.services import tutor as tutor_mod

    qid = next(iter(load_bank()))
    mock = AsyncMock(return_value=_llm_result(_tutor_payload()))
    body = {"question_id": qid, "user_question": "Walk me through the setup."}

    with patch.object(tutor_mod.llm, "agenerate", new=mock):
        await client.post("/api/lsat/tutor", json=body)
        res = await client.post("/api/lsat/tutor", json={**body, "refresh": True})

    assert mock.await_count == 2
    assert res.json()["cached"] is False


@pytest.mark.asyncio
async def test_tutor_distinct_requests_are_distinct_cache_entries(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services import tutor as tutor_mod

    qid = next(iter(load_bank()))
    mock = AsyncMock(return_value=_llm_result(_tutor_payload()))
    with patch.object(tutor_mod.llm, "agenerate", new=mock):
        await client.post(
            "/api/lsat/tutor", json={"question_id": qid, "user_question": "Why?"}
        )
        await client.post(
            "/api/lsat/tutor", json={"question_id": qid, "user_question": "How?"}
        )
    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_tutor_offline_fallback_is_never_cached(client: AsyncClient) -> None:
    from law_ai.lsat.services import tutor as tutor_mod

    qid = next(iter(load_bank()))
    body = {"question_id": qid, "user_question": "Walk me through."}

    async def boom(*args: object, **kwargs: object) -> object:
        raise tutor_mod.llm.LLMUnavailableError("down")

    with patch.object(tutor_mod.llm, "agenerate", new=boom):
        res = await client.post("/api/lsat/tutor", json=body)
    assert res.json()["used_llm"] is False

    # Chain back up: the next request must retry the LLM, not serve fallback.
    mock = AsyncMock(return_value=_llm_result(_tutor_payload()))
    with patch.object(tutor_mod.llm, "agenerate", new=mock):
        res = await client.post("/api/lsat/tutor", json=body)
    assert mock.await_count == 1
    assert res.json()["used_llm"] is True


# ---------------------------------------------------------------------------
# FR-14 — cross-check
# ---------------------------------------------------------------------------


def _verdict(choice: str) -> str:
    return json.dumps({"choice": choice, "rationale": "Because the rules force it."})


@pytest.mark.asyncio
async def test_cross_check_agreement(client: AsyncClient) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod

    qid, q = next(iter(load_bank().items()))
    with patch.object(
        cc_mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_verdict(q.correct))),
    ):
        res = await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["agree"] is True
    assert body["model_choice"] == q.correct
    assert body["bank_choice"] == q.correct
    assert body["requires_human_review"] is False


@pytest.mark.asyncio
async def test_cross_check_disagreement_flags_review(client: AsyncClient) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod

    qid, q = next(iter(load_bank().items()))
    wrong = next(c for c in ("A", "B", "C", "D", "E") if c != q.correct)
    with patch.object(
        cc_mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_verdict(wrong))),
    ):
        res = await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})
    body = res.json()
    assert body["agree"] is False
    assert body["requires_human_review"] is True

    ev = [e for e in audit_store.tail(20) if e.get("type") == "lsat_cross_check"]
    assert ev and ev[0]["agree"] is False
    assert ev[0]["requires_human_review"] is True


@pytest.mark.asyncio
async def test_cross_check_cached_on_repeat(client: AsyncClient) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod

    qid, q = next(iter(load_bank().items()))
    mock = AsyncMock(return_value=_llm_result(_verdict(q.correct)))
    with patch.object(cc_mod.llm, "agenerate", new=mock):
        first = (
            await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})
        ).json()
        second = (
            await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})
        ).json()
        forced = (
            await client.post(
                f"/api/lsat/questions/{qid}/cross-check", json={"refresh": True}
            )
        ).json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert forced["cached"] is False
    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_cross_check_offline_is_honest(client: AsyncClient) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod

    qid = next(iter(load_bank()))

    async def boom(*args: object, **kwargs: object) -> object:
        raise cc_mod.llm.LLMUnavailableError("down")

    with patch.object(cc_mod.llm, "agenerate", new=boom):
        res = await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})
    body = res.json()
    assert body["used_llm"] is False
    assert body["model_choice"] is None
    assert body["agree"] is None
    assert "unavailable" in body["rationale"]


@pytest.mark.asyncio
async def test_cross_check_unknown_question_404(client: AsyncClient) -> None:
    res = await client.post("/api/lsat/questions/nope/cross-check", json={})
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# FR-15 — validation report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_report_shape_and_counts(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/validation")
    assert res.status_code == 200
    body = res.json()
    assert body["question_count"] == len(load_bank())
    assert body["guide_count"] >= 40
    assert isinstance(body["issues"], list)
    dist = body["answer_distribution"]
    assert set(dist).issubset({"LR", "RC", "LG"})
    assert (
        sum(sum(counts.values()) for counts in dist.values()) == body["question_count"]
    )
    # `queued_reviews` counts disagreements the sweep has filed into the HITL
    # queue, so it is 0 alongside an empty `disagreements` list.
    assert body["cross_checks"] == {
        "checked": 0,
        "agreements": 0,
        "disagreements": [],
        "queued_reviews": 0,
    }


@pytest.mark.asyncio
async def test_validation_report_surfaces_cross_check_disagreements(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod

    qid, q = next(iter(load_bank().items()))
    wrong = next(c for c in ("A", "B", "C", "D", "E") if c != q.correct)
    with patch.object(
        cc_mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_verdict(wrong))),
    ):
        await client.post(f"/api/lsat/questions/{qid}/cross-check", json={})

    body = (await client.get("/api/lsat/validation")).json()
    assert body["cross_checks"]["checked"] == 1
    assert body["cross_checks"]["agreements"] == 0
    flagged = body["cross_checks"]["disagreements"]
    assert flagged and flagged[0]["question_id"] == qid
    assert flagged[0]["model_choice"] == wrong


@pytest.mark.asyncio
async def test_validation_rejects_bad_section(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/validation", params={"section": "XX"})
    assert res.status_code == 422
