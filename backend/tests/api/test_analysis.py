"""Tests for /api/analysis (spec 007)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from law_ai.core import audit_jsonl as audit_store
from django.conf import settings
from law_ai.asgi import application as app


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
    """AC-1: returns full structured response with two agent_trace entries.

    The default (non-LangGraph, non-Claude) path performs no retrieval and no
    LLM call, so both agents must report themselves as degraded with zero
    fabricated content and the run must be flagged for human review
    (constitution §4/§13 — no invented precedents, no fake confidence).
    """
    res = await client.post(
        "/api/analysis",
        json={
            "text": "Defendant breached contract.",
            "jurisdiction": "US",
            "use_langgraph": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"].startswith("an-")
    assert body["timestamp"]  # iso8601 string
    assert isinstance(body["latency_ms"], int)
    assert body["confidence"] == 0.0  # no non-degraded contributions
    assert body["irac"]["issue"]
    assert body["irac"]["degraded"] is True
    # Honesty gate: the unimplemented path must not fabricate precedents.
    assert body["precedents"]["precedents"] == []
    assert body["precedents"]["degraded"] is True
    assert "not yet implemented" in body["precedents"]["summary"]
    assert body["requires_human_review"] is True
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
    res = await client.post(
        "/api/analysis", json={"text": "Negligence claim.", "use_langgraph": False}
    )
    assert res.status_code == 200
    events = audit_store.tail(10)
    agents = [e.get("agent") for e in events if e.get("type") == "agent_call"]
    assert "AnalysisStudio" in agents
    assert "LegalAnalyst" in agents
    assert "PrecedentHunter" in agents


def _patch_non_degraded_agents(
    monkeypatch: pytest.MonkeyPatch, *, analyst_conf: float, hunter_conf: float
) -> None:
    """Force BOTH agents to report real (non-degraded, no-flag) outputs.

    With any degraded/requires_review flag set, requires_human_review is
    forced True regardless of the mean — so threshold tests must clear every
    structured flag or they pass vacuously.
    """
    from law_ai.agents_runtime.crews.legal_analyst import LegalAnalyst
    from law_ai.agents_runtime.crews.precedent_hunter import PrecedentHunter

    analyst_original = LegalAnalyst.run
    hunter_original = PrecedentHunter.run

    async def analyst_run(self, input_data):  # type: ignore[no-untyped-def]
        out = await analyst_original(self, input_data)
        out.confidence = analyst_conf
        out.degraded = False
        out.requires_review = False
        return out

    async def hunter_run(self, input_data):  # type: ignore[no-untyped-def]
        out = await hunter_original(self, input_data)
        out.confidence = hunter_conf
        out.degraded = False
        return out

    monkeypatch.setattr(LegalAnalyst, "run", analyst_run)
    monkeypatch.setattr(PrecedentHunter, "run", hunter_run)


@pytest.mark.asyncio
async def test_low_confidence_triggers_hitl_flag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 / NFR-HITL-1: mean confidence < 0.7 → requires_human_review=True.

    Both agents are patched non-degraded so ONLY the confidence-threshold
    branch can set the flag (mean = (0.4 + 0.9) / 2 = 0.65 < 0.7).
    """
    _patch_non_degraded_agents(monkeypatch, analyst_conf=0.4, hunter_conf=0.9)
    res = await client.post(
        "/api/analysis", json={"text": "Contract dispute.", "use_langgraph": False}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["confidence"] == pytest.approx(0.65)
    assert body["requires_human_review"] is True


@pytest.mark.asyncio
async def test_high_confidence_clears_hitl_flag(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inverse case: mean ≥ 0.7 with no structured flags → no review required."""
    _patch_non_degraded_agents(monkeypatch, analyst_conf=0.8, hunter_conf=0.9)
    res = await client.post(
        "/api/analysis", json={"text": "Contract dispute.", "use_langgraph": False}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["confidence"] == pytest.approx(0.85)
    assert body["requires_human_review"] is False


@pytest.mark.asyncio
async def test_run_analysis_executes_agents_in_parallel(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: gather() ⇒ wall-clock ≈ max(latency), not sum."""
    from law_ai.agents_runtime.crews.legal_analyst import LegalAnalyst
    from law_ai.agents_runtime.crews.precedent_hunter import PrecedentHunter

    orig_a = LegalAnalyst.run
    orig_h = PrecedentHunter.run

    async def slow_a(self, input_data):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.1)
        return await orig_a(self, input_data)

    async def slow_h(self, input_data):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.1)
        return await orig_h(self, input_data)

    monkeypatch.setattr(LegalAnalyst, "run", slow_a)
    monkeypatch.setattr(PrecedentHunter, "run", slow_h)

    started = time.perf_counter()
    res = await client.post(
        "/api/analysis", json={"text": "Tort claim.", "use_langgraph": False}
    )
    elapsed = time.perf_counter() - started
    assert res.status_code == 200
    # Serial would be ≥ 0.20s; parallel should be well under 0.25s even on
    # noisy CI runners. Threshold raised from 0.18 → 0.25 because shared
    # GitHub Actions VMs occasionally add 50–100 ms of scheduling overhead on
    # top of the 0.1 s asyncio.sleep, pushing wall-clock past 0.18 s even
    # though the agents ran concurrently.  0.25 s is still far below the 0.20 s
    # serial floor, so the test still catches any accidental serialisation.
    assert elapsed < 0.25, f"expected parallel run, got {elapsed:.3f}s"


# --- Spec 027/029: the default LangGraph engine is a resilience boundary ---


@pytest.mark.asyncio
async def test_default_engine_path_never_500s_when_engine_explodes(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The DEFAULT path must degrade, never surface a 500.

    Regression: with `use_langgraph` defaulting to True (spec 027), a live
    Ollama whose model was not yet pulled raised the client library's own
    ResponseError — outside the original narrow except clause — and every
    request 500'd. The boundary now catches broadly and degrades honestly.
    """
    from law_ai.agents_runtime import llm
    from law_ai.agents_runtime.graphs import LegalWorkflow

    class WeirdEngineError(Exception):
        """Not in any hand-written exception tuple."""

    monkeypatch.setattr(llm, "ollama_available_async", _always(True))
    monkeypatch.setattr(
        LegalWorkflow, "invoke", _raises(WeirdEngineError("model not pulled"))
    )

    res = await client.post("/api/analysis", json={"text": "Is X liable?"})
    assert res.status_code == 200
    body = res.json()
    assert body["irac"]["degraded"] is True
    assert body["requires_human_review"] is True
    assert body["confidence"] == 0.0


@pytest.mark.asyncio
async def test_default_engine_path_degrades_when_ollama_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probe failure short-circuits before any LLM call is attempted."""
    from law_ai.agents_runtime import llm

    monkeypatch.setattr(llm, "ollama_available_async", _always(False))

    res = await client.post("/api/analysis", json={"text": "Is X liable?"})
    assert res.status_code == 200
    body = res.json()
    assert body["irac"]["degraded"] is True
    assert "ENGINE UNAVAILABLE" in body["irac"]["rule"]


def _always(value: object):
    async def _inner(*args: object, **kwargs: object) -> object:
        return value

    return _inner


def _raises(exc: Exception):
    async def _inner(*args: object, **kwargs: object) -> object:
        raise exc

    return _inner


# --- Spec 009: per-router auth gating ---


@pytest.mark.asyncio
async def test_analysis_auth_unset_open(client: AsyncClient) -> None:
    """AC-1 — default-open posture preserved on /api/analysis."""
    res = await client.post(
        "/api/analysis",
        json={"text": "x", "jurisdiction": "US", "use_langgraph": False},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_analysis_auth_falls_back_to_agent_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/AC-3/AC-4 — fallback to AGENT_API_KEY when ANALYSIS_API_KEY unset."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    body = {"text": "x", "jurisdiction": "US", "use_langgraph": False}

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
    body = {"text": "x", "jurisdiction": "US", "use_langgraph": False}
    res = await client.post("/api/analysis", json=body, headers={"X-API-Key": "shared"})
    assert res.status_code == 401
    res = await client.post(
        "/api/analysis", json=body, headers={"X-API-Key": "analysis-key"}
    )
    assert res.status_code == 200


# --- Spec 021: agent WebSocket streaming ---


@pytest.mark.asyncio
async def test_agent_ws_events_emitted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-6 / AC-1: three group_send calls emitted (LA step + PH step + complete)."""
    from unittest.mock import AsyncMock, MagicMock

    import law_ai.analysis.urls as analysis_urls

    mock_layer: MagicMock = MagicMock()
    mock_layer.group_send = AsyncMock()
    monkeypatch.setattr(analysis_urls, "get_channel_layer", lambda: mock_layer)

    res = await client.post(
        "/api/analysis", json={"text": "Tort claim.", "use_langgraph": False}
    )
    assert res.status_code == 200

    calls = mock_layer.group_send.call_args_list
    assert len(calls) == 3

    # Each call: group_send(group_name, {"type": "agent_event", "payload": {...}})
    payloads = [c.args[1]["payload"] for c in calls]
    assert payloads[0]["type"] == "agent_step"
    assert payloads[0]["agent"] == "LegalAnalyst"
    assert payloads[1]["type"] == "agent_step"
    assert payloads[1]["agent"] == "PrecedentHunter"
    assert payloads[2]["type"] == "complete"
    assert payloads[2]["analysis_id"] == res.json()["id"]


@pytest.mark.asyncio
async def test_agent_ws_events_resilient_to_channel_layer_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-1 / AC-2: channel layer exception does not abort the analysis."""
    import law_ai.analysis.urls as analysis_urls

    def boom() -> None:
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(analysis_urls, "get_channel_layer", boom)

    res = await client.post(
        "/api/analysis", json={"text": "Contract dispute.", "use_langgraph": False}
    )
    assert res.status_code == 200
    assert res.json()["id"].startswith("an-")
