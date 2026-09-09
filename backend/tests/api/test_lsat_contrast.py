"""Contrast + variation endpoints (spec 054 AC-2, AC-6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from django.conf import settings
from httpx import ASGITransport, AsyncClient

from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.asyncio
async def test_contrast_set_hides_notes_until_spoilers(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/questions/lr-002/contrast")
    assert res.status_code == 200
    body = res.json()
    assert body["root_id"] == "lr-002" and body["count"] >= 3
    assert all("contrast_note" not in m and "correct" not in m for m in body["members"])
    res = await client.get(
        "/api/lsat/questions/lr-097/contrast", params={"spoilers": "1"}
    )
    assert res.json()["root_id"] == "lr-002"
    assert next(m for m in res.json()["members"] if m["id"] == "lr-097")[
        "contrast_note"
    ]
    assert (await client.get("/api/lsat/questions/nope/contrast")).status_code == 404


@pytest.mark.asyncio
async def test_question_payload_names_its_root_but_not_its_type(
    client: AsyncClient,
) -> None:
    res = await client.get("/api/lsat/questions/lr-097")
    assert res.status_code == 200
    assert res.json()["variation_of"] == "lr-002"
    assert "archetype" not in res.json() and "contrast_note" not in res.json()


@pytest.mark.asyncio
async def test_variation_endpoint_validates_and_relays_the_loop(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services.contrast import VariationResult

    res = await client.post(
        "/api/lsat/questions/lr-002/variations",
        json={"target_archetype_id": "lr-bogus"},
    )
    assert res.status_code == 422
    assert (
        await client.post(
            "/api/lsat/questions/nope/variations",
            json={"target_archetype_id": "lr-weaken"},
        )
    ).status_code == 404
    ok = VariationResult(
        source_id="lr-002",
        target_archetype_id="lr-strengthen",
        proposal_id="prop-1",
        accepted=True,
        rounds=2,
    )
    with patch("law_ai.lsat.urls.draft_variation", new=AsyncMock(return_value=ok)):
        res = await client.post(
            "/api/lsat/questions/lr-002/variations",
            json={"target_archetype_id": "lr-strengthen", "max_rounds": 2},
        )
    assert res.status_code == 202 and res.json()["proposal_id"] == "prop-1"
    down = VariationResult(
        source_id="lr-002", target_archetype_id="lr-strengthen", degraded=True
    )
    with patch("law_ai.lsat.urls.draft_variation", new=AsyncMock(return_value=down)):
        res = await client.post(
            "/api/lsat/questions/lr-002/variations",
            json={"target_archetype_id": "lr-strengthen"},
        )
    assert res.status_code == 503


@pytest.mark.asyncio
async def test_review_endpoint_relays_the_loop(client: AsyncClient) -> None:
    from law_ai.lsat.services.rewrite import ReviewResult

    assert (
        await client.post("/api/lsat/questions/nope/review", json={})
    ).status_code == 404
    clean = ReviewResult(question_id="lr-002", verdict="pass", clean=True)
    with patch("law_ai.lsat.urls.review_question", new=AsyncMock(return_value=clean)):
        res = await client.post("/api/lsat/questions/lr-002/review", json={})
    assert res.status_code == 202 and res.json()["clean"] is True
    down = ReviewResult(question_id="lr-002", degraded=True)
    with patch("law_ai.lsat.urls.review_question", new=AsyncMock(return_value=down)):
        res = await client.post(
            "/api/lsat/questions/lr-002/review", json={"max_rounds": 2}
        )
    assert res.status_code == 503
