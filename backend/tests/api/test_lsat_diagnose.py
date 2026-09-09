"""Tests for the diagnosis + playbook endpoints (spec 053 AC-3, AC-4, AC-6, AC-7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from django.conf import settings
from django.contrib.auth import get_user_model
from httpx import ASGITransport, AsyncClient

from law_ai.asgi import application as app
from law_ai.core import audit_jsonl as audit_store
from law_ai.lsat.services.bank import load_bank


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_diagnose_deals_options_without_the_key(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/questions/lr-002/diagnose")
    assert res.status_code == 200
    body = res.json()
    assert body["question_id"] == "lr-002" and body["section"] == "LR"
    ids = [o["id"] for o in body["type_options"]]
    assert "lr-weaken" in ids and len(ids) == 5
    assert body["strategy_options"]
    assert "archetype_id" not in body and "correct" not in body


@pytest.mark.asyncio
async def test_get_diagnose_unknown_question_404(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/questions/nope-999/diagnose")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_post_diagnose_grades_and_audits(client: AsyncClient) -> None:
    res = await client.post(
        "/api/lsat/questions/lr-002/diagnose",
        json={"archetype_id": "lr-strengthen", "strategy_id": "attack-the-link"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["archetype_id"] == "lr-weaken"
    assert body["archetype_correct"] is False
    assert body["family_correct"] is True  # strengthen and weaken share a family
    assert body["strategy_correct"] is True
    assert body["playbook"]["name"] == "Weaken"
    assert body["playbook"]["traps"]
    events = [e for e in audit_store.tail(50) if e.get("type") == "lsat_diagnose"]
    assert len(events) == 1
    assert events[0]["chosen_archetype"] == "lr-strengthen"
    assert events[0]["archetype_correct"] is False


@pytest.mark.asyncio
async def test_post_diagnose_rejects_unknown_type_and_strategy(
    client: AsyncClient,
) -> None:
    res = await client.post(
        "/api/lsat/questions/lr-002/diagnose", json={"archetype_id": "lr-bogus"}
    )
    assert res.status_code == 422
    res = await client.post(
        "/api/lsat/questions/lr-002/diagnose",
        json={"archetype_id": "lr-weaken", "strategy_id": "bogus"},
    )
    assert res.status_code == 422
    res = await client.post("/api/lsat/questions/lr-002/diagnose", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_anonymous_stats_fold_diagnosis_from_audit(client: AsyncClient) -> None:
    await client.post(
        "/api/lsat/questions/lr-002/diagnose", json={"archetype_id": "lr-weaken"}
    )
    await client.post(
        "/api/lsat/questions/lr-002/diagnose", json={"archetype_id": "lr-strengthen"}
    )
    res = await client.get("/api/lsat/stats")
    assert res.status_code == 200
    diag = res.json()["diagnosis"]
    assert diag["attempts"] == 2 and diag["type_correct"] == 1
    assert diag["confusions"] == [
        {"chosen": "lr-strengthen", "actual": "lr-weaken", "count": 1}
    ]
    # A keyed-section filter keeps only that section's diagnoses.
    res = await client.get("/api/lsat/stats", params={"section": "RC"})
    assert res.json()["diagnosis"]["attempts"] == 0


@pytest.mark.django_db
def test_signed_in_diagnosis_is_recorded_per_learner() -> None:
    from rest_framework.test import APIClient

    from law_ai.lsat.models import LsatDiagnosisAttempt

    user = get_user_model().objects.create_user(username="diag", password="pw-123456")
    client = APIClient()
    client.force_login(user)
    res = client.post(
        "/api/lsat/questions/lr-005/diagnose",
        {"archetype_id": "lr-flaw-general", "strategy_id": "name-the-flaw"},
        format="json",
    )
    assert res.status_code == 200
    rows = list(LsatDiagnosisAttempt.objects.filter(user=user))
    assert len(rows) == 1
    assert rows[0].archetype_id == "lr-causal-flaw"
    assert rows[0].family_correct is True and rows[0].archetype_correct is False
    assert rows[0].strategy_correct is True
    stats = client.get("/api/lsat/stats").json()
    assert stats["scope"] == "user"
    assert stats["diagnosis"]["attempts"] == 1
    assert stats["diagnosis"]["confusions"][0]["actual"] == "lr-causal-flaw"
    # Diagnoses never enter the answer-accuracy denominator (AC-6).
    assert stats["attempts"] == 0


@pytest.mark.asyncio
async def test_playbooks_index_and_detail(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/playbooks", params={"section": "LG"})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 10 and all(b["section"] == "LG" for b in body["playbooks"])
    assert body["strategies"] and body["traps"]
    res = await client.get("/api/lsat/playbooks/lr-necessary-assumption")
    assert res.status_code == 200
    detail = res.json()
    assert detail["name"] == "Necessary Assumption"
    assert "lr-assumption-family" in [a["id"] for a in detail["taught_in"]]
    assert detail["question_count"] >= 1
    assert res.json()["difficulty_weights"]
    assert (await client.get("/api/lsat/playbooks/nope")).status_code == 404
    assert (
        await client.get("/api/lsat/playbooks", params={"section": "WS"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_questions_filter_by_archetype(client: AsyncClient) -> None:
    res = await client.get(
        "/api/lsat/questions", params={"archetype": "lr-weaken", "limit": 25}
    )
    assert res.status_code == 200
    ids = {q["id"] for q in res.json()["questions"]}
    bank = load_bank()
    assert ids and all(bank[i].archetype == "lr-weaken" for i in ids)
    # The stamp itself is never shipped to the client: it is the exercise's key.
    assert all("archetype" not in q for q in res.json()["questions"])
