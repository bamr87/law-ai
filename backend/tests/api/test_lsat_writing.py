"""Tests for /api/lsat/writing/* (spec 047 FR-5, AC-3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings
from law_ai.asgi import application as app
from law_ai.lsat.services.writing import load_writing_prompts, rubric_for

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _prompt() -> Any:
    return next(iter(load_writing_prompts().values()))


def _draft() -> str:
    return (
        "The council should fund the rail extension because it is the only "
        "option that reaches residents who cannot drive. " * 12
    )


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model_label = "test/model"


def _evaluation_payload() -> str:
    rubric = rubric_for(_prompt())
    return json.dumps(
        {
            "evaluation": {
                "position_taken": _prompt().positions[0].id,
                "summary": "Clear thesis, thin rebuttal.",
                "criteria": [
                    {
                        "criterion_id": c.id,
                        "band": 3,
                        "evidence": "reaches residents who cannot drive",
                        "improvement": "Name the standard explicitly.",
                    }
                    for c in rubric.criteria
                ],
                "strengths": ["clear thesis"],
                "priorities": ["answer the cost objection"],
            }
        }
    )


# ---------------------------------------------------------------------------
# AC-3 — listing and detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_prompts_without_model_responses(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/lsat/writing/prompts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(load_writing_prompts())
    assert body["count"] > 0
    raw = json.dumps(body)
    for payload in body["prompts"]:
        assert "model_response" not in payload
        assert payload["has_model_response"] is True
    for prompt in load_writing_prompts().values():
        assert prompt.model_response.essay[:60] not in raw
        assert prompt.model_response.thesis not in raw


@pytest.mark.asyncio
async def test_list_is_ordered_by_id(client: AsyncClient) -> None:
    body = (await client.get("/api/lsat/writing/prompts")).json()
    ids = [p["id"] for p in body["prompts"]]
    assert ids == sorted(ids)


@pytest.mark.asyncio
async def test_list_filters_by_difficulty(client: AsyncClient) -> None:
    resp = await client.get("/api/lsat/writing/prompts?difficulty=easy")
    assert resp.status_code == 200
    assert all(p["difficulty"] == "easy" for p in resp.json()["prompts"])


@pytest.mark.asyncio
async def test_bad_difficulty_is_unprocessable(client: AsyncClient) -> None:
    resp = await client.get("/api/lsat/writing/prompts?difficulty=impossible")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_detail_withholds_the_model_response_by_default(
    client: AsyncClient,
) -> None:
    prompt = _prompt()
    resp = await client.get(f"/api/lsat/writing/prompts/{prompt.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "model_response" not in body
    assert body["rubric"]["id"] == prompt.rubric_id
    # The rubric ships pre-draft on purpose: self-scoring needs it.
    assert body["rubric"]["criteria"]
    assert body["prompt"]["self_check"]


@pytest.mark.asyncio
async def test_detail_returns_the_model_response_on_request(
    client: AsyncClient,
) -> None:
    prompt = _prompt()
    resp = await client.get(f"/api/lsat/writing/prompts/{prompt.id}?model_response=1")
    assert resp.status_code == 200
    model = resp.json()["model_response"]
    assert model["essay"] == prompt.model_response.essay
    assert {a["criterion_id"] for a in model["annotations"]} == set(
        rubric_for(prompt).criterion_ids
    )


@pytest.mark.asyncio
async def test_unknown_prompt_is_404(client: AsyncClient) -> None:
    assert (await client.get("/api/lsat/writing/prompts/nope")).status_code == 404


@pytest.mark.asyncio
async def test_rubric_endpoint_returns_the_default(client: AsyncClient) -> None:
    resp = await client.get("/api/lsat/writing/rubric")
    assert resp.status_code == 200
    rubric = resp.json()["rubric"]
    assert rubric["bands"] and rubric["criteria"]
    assert sum(c["weight"] for c in rubric["criteria"]) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_rubric_endpoint_404s_on_unknown_id(client: AsyncClient) -> None:
    resp = await client.get("/api/lsat/writing/rubric?id=nope")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Sections payload carries the writing inventory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sections_report_writing_prompt_count(client: AsyncClient) -> None:
    body = (await client.get("/api/lsat/sections")).json()
    by_code = {s["code"]: s for s in body["sections"]}
    assert by_code["WS"]["writing_prompt_count"] == len(load_writing_prompts())
    # WS has no keyed questions — the two counts must not be conflated.
    assert by_code["WS"]["question_count"] == 0
    assert by_code["LR"]["writing_prompt_count"] == 0
    assert by_code["LR"]["question_count"] > 0


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_returns_bands_with_provenance(client: AsyncClient) -> None:
    from law_ai.core import llm

    prompt = _prompt()
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(_evaluation_payload()))
    ):
        resp = await client.post(
            "/api/lsat/writing/evaluate",
            json={"prompt_id": prompt.id, "response": _draft()},
        )
    assert resp.status_code == 200
    body = resp.json()
    # NFR-PROV-1: the producing model and prompt version travel with the bands.
    assert body["model"] == "test/model"
    assert body["prompt_version"].startswith("lsat_writing_evaluator/")
    assert body["degraded"] is False
    assert len(body["evaluation"]["criteria"]) == len(rubric_for(prompt).criterion_ids)


@pytest.mark.asyncio
async def test_evaluate_records_an_audit_event(
    client: AsyncClient, tmp_path: Path
) -> None:
    from law_ai.core import audit_jsonl as audit_store
    from law_ai.core import llm

    prompt = _prompt()
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(_evaluation_payload()))
    ):
        await client.post(
            "/api/lsat/writing/evaluate",
            json={"prompt_id": prompt.id, "response": _draft()},
        )
    events = [
        e for e in audit_store.tail(50) if e.get("type") == "lsat_writing_evaluate"
    ]
    assert events, "no lsat_writing_evaluate audit event recorded"
    assert events[-1]["prompt_id"] == prompt.id
    assert events[-1]["section"] == "WS"


@pytest.mark.asyncio
async def test_evaluate_rejects_a_too_short_response(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/lsat/writing/evaluate",
        json={"prompt_id": _prompt().id, "response": "too short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_evaluate_404s_on_unknown_prompt(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/lsat/writing/evaluate",
        json={"prompt_id": "nope", "response": _draft()},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_evaluate_degrades_rather_than_erroring_offline(
    client: AsyncClient,
) -> None:
    from law_ai.core import llm

    with patch.object(
        llm,
        "agenerate",
        new=AsyncMock(side_effect=llm.LLMUnavailableError("no providers")),
    ):
        resp = await client.post(
            "/api/lsat/writing/evaluate",
            json={"prompt_id": _prompt().id, "response": _draft()},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["confidence"] == 0.0
    assert "OFFLINE FALLBACK" in body["evaluation"]["summary"]
