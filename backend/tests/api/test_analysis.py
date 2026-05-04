"""Tests for /api/analysis (spec 007)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lexgraph.core import audit_jsonl as audit_store
from django.conf import settings
from lexgraph.asgi import application as app


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
async def test_run_analysis_happy_path(client: AsyncClient) -> None:
    """AC-1: returns full structured response with two agent_trace entries."""
    res = await client.post(
        "/api/analysis",
        json={"text": "Defendant breached contract.", "jurisdiction": "US"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"].startswith("an-")
    assert body["timestamp"]  # iso8601 string
    assert isinstance(body["latency_ms"], int)
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["irac"]["issue"]
    assert body["precedents"]["precedents"]
    assert len(body["agent_trace"]) == 2
    agents = {entry["agent"] for entry in body["agent_trace"]}
    assert agents == {"LegalAnalyst", "PrecedentHunter"}
    for entry in body["agent_trace"]:
        assert entry["trace_id"] is not None


@pytest.mark.asyncio
async def test_run_analysis_rejects_empty_text(client: AsyncClient) -> None:
    """AC-2: empty text → 422."""
    res = await client.post("/api/analysis", json={"text": ""})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_run_analysis_rejects_oversized_text(client: AsyncClient) -> None:
    """FR-1: text > 20_000 chars → 422."""
    res = await client.post("/api/analysis", json={"text": "x" * 20_001})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_run_analysis_emits_three_audit_events(client: AsyncClient) -> None:
    """AC-3 / NFR-AUDIT-1: one umbrella + two child events."""
    res = await client.post("/api/analysis", json={"text": "Negligence claim."})
    assert res.status_code == 200
    events = audit_store.tail(10)
    agents = [e.get("agent") for e in events if e.get("type") == "agent_call"]
    assert "AnalysisStudio" in agents
    assert "LegalAnalyst" in agents
    assert "PrecedentHunter" in agents


@pytest.mark.asyncio
async def test_low_confidence_triggers_hitl_flag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 / NFR-HITL-1: mean confidence < 0.7 → requires_human_review=True."""
    from lexgraph.agents_runtime.crews.legal_analyst import LegalAnalyst

    original = LegalAnalyst.run

    async def low_conf(self, input_data):  # type: ignore[no-untyped-def]
        out = await original(self, input_data)
        out.confidence = 0.4
        return out

    monkeypatch.setattr(LegalAnalyst, "run", low_conf)
    res = await client.post("/api/analysis", json={"text": "Contract dispute."})
    assert res.status_code == 200
    body = res.json()
    assert body["confidence"] < 0.7
    assert body["requires_human_review"] is True


@pytest.mark.asyncio
async def test_run_analysis_executes_agents_in_parallel(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: gather() ⇒ wall-clock ≈ max(latency), not sum."""
    from lexgraph.agents_runtime.crews.legal_analyst import LegalAnalyst
    from lexgraph.agents_runtime.crews.precedent_hunter import PrecedentHunter

    orig_a = LegalAnalyst.run
    orig_h = PrecedentHunter.run

    async def slow_a(self, input_data):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)
        return await orig_a(self, input_data)

    async def slow_h(self, input_data):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.05)
        return await orig_h(self, input_data)

    monkeypatch.setattr(LegalAnalyst, "run", slow_a)
    monkeypatch.setattr(PrecedentHunter, "run", slow_h)

    started = time.perf_counter()
    res = await client.post("/api/analysis", json={"text": "Tort claim."})
    elapsed = time.perf_counter() - started
    assert res.status_code == 200
    # Serial would be ≥ 0.10s; parallel should comfortably be < 0.09s.
    assert elapsed < 0.09, f"expected parallel run, got {elapsed:.3f}s"


# --- Spec 009: per-router auth gating ---


@pytest.mark.asyncio
async def test_analysis_auth_unset_open(client: AsyncClient) -> None:
    """AC-1 — default-open posture preserved on /api/analysis."""
    res = await client.post("/api/analysis", json={"text": "x", "jurisdiction": "US"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_analysis_auth_falls_back_to_agent_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/AC-3/AC-4 — fallback to AGENT_API_KEY when ANALYSIS_API_KEY unset."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    body = {"text": "x", "jurisdiction": "US"}

    res = await client.post("/api/analysis", json=body)
    assert res.status_code == 401
    assert res.json()["detail"] == "missing api key"

    res = await client.post("/api/analysis", json=body, headers={"X-API-Key": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid api key"

    res = await client.post("/api/analysis", json=body, headers={"X-API-Key": "shared"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_analysis_per_router_override(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANALYSIS_API_KEY override is enforced; shared key is rejected."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    monkeypatch.setattr(settings, "ANALYSIS_API_KEY", "analysis-key")
    body = {"text": "x", "jurisdiction": "US"}
    res = await client.post("/api/analysis", json=body, headers={"X-API-Key": "shared"})
    assert res.status_code == 401
    res = await client.post(
        "/api/analysis", json=body, headers={"X-API-Key": "analysis-key"}
    )
    assert res.status_code == 200
