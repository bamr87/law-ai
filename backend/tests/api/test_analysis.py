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
    # Honesty gate: an empty corpus must not fabricate precedents, and the
    # summary must read as "not in this corpus", never "no such precedent"
    # (BL-20260511-06 replaced the unimplemented stub with real GraphRAG
    # retrieval; the empty test graph still yields zero rows).
    assert body["precedents"]["precedents"] == []
    assert body["precedents"]["degraded"] is True
    assert body["precedents"]["confidence"] == 0.0
    assert "does NOT mean no relevant precedent exists" in body["precedents"]["summary"]
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

    # The emitter moved to law_ai.agentsapi.streaming so the LSAT tutor and the
    # autonomy cycle can share it (BL-20260811-15); analysis/urls.py now calls
    # through to it, so that is where the channel layer is looked up.
    from law_ai.agentsapi import streaming

    mock_layer: MagicMock = MagicMock()
    mock_layer.group_send = AsyncMock()
    monkeypatch.setattr(streaming, "get_channel_layer", lambda: mock_layer)

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
    from law_ai.agentsapi import streaming

    def boom() -> None:
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(streaming, "get_channel_layer", boom)

    res = await client.post(
        "/api/analysis", json={"text": "Contract dispute.", "use_langgraph": False}
    )
    assert res.status_code == 200
    assert res.json()["id"].startswith("an-")


# ---------------------------------------------------------------------------
# BL-20260810-13: durable LangGraph threads on the default path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_id_is_validated_like_stream_id(client: AsyncClient) -> None:
    res = await client.post(
        "/api/analysis",
        json={"text": "x", "thread_id": "bad id!", "use_langgraph": False},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_thread_id_reaches_the_workflow(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API's thread_id is what LegalWorkflow.invoke is asked to resume."""
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import (
        LegalWorkflow,
        LegalWorkflowOutput,
    )

    seen: dict[str, object] = {}

    async def fake_invoke(self, question, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return LegalWorkflowOutput(
            answer="a", citations=[], confidence=0.9, langgraph_thread_id="thread-x"
        )

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield object()

    async def fake_ready():  # type: ignore[no-untyped-def]
        return True, ""

    async def fake_has_state(workflow, thread_id):  # type: ignore[no-untyped-def]
        return thread_id == "thread-x"

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_has_state", fake_has_state)

    res = await client.post(
        "/api/analysis",
        json={"text": "Is X liable?", "thread_id": "thread-x", "use_langgraph": True},
    )
    assert res.status_code == 200
    assert seen.get("thread_id") == "thread-x"
    body = res.json()
    assert body["resumed"] is True
    assert body["irac"]["langgraph_thread_id"] == "thread-x"


@pytest.mark.asyncio
async def test_fresh_thread_is_not_reported_as_resumed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import (
        LegalWorkflow,
        LegalWorkflowOutput,
    )

    async def fake_invoke(self, question, **kwargs):  # type: ignore[no-untyped-def]
        return LegalWorkflowOutput(
            answer="a", citations=[], confidence=0.9, langgraph_thread_id="lwf-new"
        )

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield object()

    async def fake_ready():  # type: ignore[no-untyped-def]
        return True, ""

    async def no_state(workflow, thread_id):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_has_state", no_state)

    res = await client.post("/api/analysis", json={"text": "q", "use_langgraph": True})
    assert res.status_code == 200
    assert res.json()["resumed"] is False


@pytest.mark.asyncio
async def test_unopenable_checkpointer_still_runs_the_analysis(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing resumability must not fail an analysis."""
    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs import runtime as rt

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("no postgres")

    monkeypatch.setattr(rt, "build_checkpointer", boom)
    async with mod._analysis_checkpointer() as saver:
        assert saver is None


@pytest.mark.asyncio
async def test_thread_lookup_endpoint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import asynccontextmanager

    from law_ai.analysis import urls as analysis_urls

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield object()

    class _Snapshot:
        values = {
            "question": "Is X liable?",
            "jurisdiction": "us-ca",
            "case_id": None,
            "retrieved": [{}, {}],
            "citations": [{}],
        }

    async def fake_get_state(self, thread_id):  # type: ignore[no-untyped-def]
        return _Snapshot() if thread_id == "known" else type("E", (), {"values": {}})()

    pytest.importorskip("langgraph")
    from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflow

    monkeypatch.setattr(analysis_urls, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(LegalWorkflow, "get_state", fake_get_state)

    known = await client.get("/api/analysis/threads/known")
    assert known.status_code == 200
    assert known.json() == {
        "thread_id": "known",
        "exists": True,
        "question": "Is X liable?",
        "jurisdiction": "us-ca",
        "case_id": None,
        "retrieved_count": 2,
        "citation_count": 1,
    }

    missing = await client.get("/api/analysis/threads/never-seen")
    assert missing.status_code == 200
    assert missing.json() == {"thread_id": "never-seen", "exists": False}


@pytest.mark.asyncio
async def test_thread_lookup_rejects_a_malformed_id(client: AsyncClient) -> None:
    res = await client.get("/api/analysis/threads/bad%20id")
    assert res.status_code == 400
