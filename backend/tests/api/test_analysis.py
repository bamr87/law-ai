"""Tests for /api/analysis (spec 007)."""

from __future__ import annotations

import asyncio
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
    """AC-5: gather() ⇒ both agents are in flight at the same time.

    Asserted structurally rather than against the wall clock. Each patched agent
    announces that it has started, then waits for the *other* to have started.
    Under ``gather`` both reach the rendezvous at once. If the endpoint ever
    awaited them one after the other, the first would wait for an agent that has
    not begun and hit the timeout, which is recorded and fails the test.

    The earlier ``elapsed < 0.25`` check sat only 50 ms above its own serial
    floor (0.20 s) and had already been loosened once (0.18 → 0.25) for shared
    GitHub Actions runners; a loaded runner still pushed it over (0.260 s). No
    threshold here depends on how busy the runner is.
    """
    from law_ai.agents_runtime.crews.legal_analyst import LegalAnalyst
    from law_ai.agents_runtime.crews.precedent_hunter import PrecedentHunter

    orig_a = LegalAnalyst.run
    orig_h = PrecedentHunter.run

    both_started = asyncio.Event()
    started: list[str] = []
    timed_out: list[str] = []

    async def rendezvous(name: str) -> None:
        started.append(name)
        if len(started) == 2:
            both_started.set()
        try:
            # Normally a microsecond handshake; the deadline is only ever
            # consumed when execution is serial.
            await asyncio.wait_for(both_started.wait(), timeout=2)
        except TimeoutError:
            # Recorded rather than relied on: the endpoint degrades a failing
            # agent instead of raising, so the exception alone may never reach
            # the test.
            timed_out.append(name)
            raise

    async def slow_a(self, input_data):  # type: ignore[no-untyped-def]
        await rendezvous("LegalAnalyst")
        return await orig_a(self, input_data)

    async def slow_h(self, input_data):  # type: ignore[no-untyped-def]
        await rendezvous("PrecedentHunter")
        return await orig_h(self, input_data)

    monkeypatch.setattr(LegalAnalyst, "run", slow_a)
    monkeypatch.setattr(PrecedentHunter, "run", slow_h)

    res = await client.post(
        "/api/analysis", json={"text": "Tort claim.", "use_langgraph": False}
    )
    assert res.status_code == 200
    assert sorted(started) == ["LegalAnalyst", "PrecedentHunter"]
    why = f"agents ran serially: {timed_out} waited for an agent that had not started"
    assert not timed_out, why


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
    from law_ai.agents_runtime.crews.precedent_hunter import PrecedentHunter
    from law_ai.agents_runtime.graphs import LegalWorkflow

    class WeirdEngineError(Exception):
        """Not in any hand-written exception tuple."""

    monkeypatch.setattr(llm, "ollama_available_async", _always(True))
    monkeypatch.setattr(
        LegalWorkflow, "invoke", _raises(WeirdEngineError("model not pulled"))
    )
    # BL-20260905-78/97: the assertion below is about the *analyst* boundary,
    # but `confidence` is the mean over non-degraded agents — so a shared
    # Neo4j that happens to hold :Case rows made the hunter succeed and the
    # mean drift off 0.0. Pin the retrieval half to a degraded result so this
    # test measures the engine boundary and nothing else.
    monkeypatch.setattr(PrecedentHunter, "run", _degraded_hunter())

    res = await client.post("/api/analysis", json={"text": "Is X liable?"})
    assert res.status_code == 200
    body = res.json()
    assert body["irac"]["degraded"] is True
    assert body["requires_human_review"] is True
    # No non-degraded contribution on either side ⇒ no fabricated confidence.
    assert body["agent_trace"][0]["confidence"] == 0.0
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


def _degraded_hunter():
    """A ``PrecedentHunter.run`` replacement that never touches Neo4j.

    Keeps tests that assert on the aggregate confidence independent of
    whatever rows the shared dev graph happens to hold (BL-20260905-78 /
    BL-20260905-97).
    """
    from law_ai.agents_runtime.crews.precedent_hunter import PrecedentList

    async def _inner(self: object, *args: object, **kwargs: object) -> PrecedentList:
        return PrecedentList(
            precedents=[],
            summary="retrieval stubbed out for this test",
            confidence=0.0,
            degraded=True,
        )

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
        # Same question the request below sends, so the BL-20260905-81
        # continuity check sees a matching resume.
        return {"question": "Is X liable?"} if thread_id == "thread-x" else {}

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_state_values", fake_has_state)

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
        return {}

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_state_values", no_state)

    res = await client.post("/api/analysis", json={"text": "q", "use_langgraph": True})
    assert res.status_code == 200
    assert res.json()["resumed"] is False


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"text": "A completely different question?"}, "question"),
        ({"text": "Is X liable?", "jurisdiction": "us-ny"}, "jurisdiction"),
    ],
)
@pytest.mark.asyncio
async def test_divergent_resume_is_refused_with_409(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    field: str,
) -> None:
    """BL-20260905-81: a resume may not quietly rewrite the thread's ask.

    The checkpointed channels record what was asked; resuming with a
    different question or jurisdiction used to overwrite them in place, so
    the earlier run stopped being reproducible from its own thread.
    """
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflow

    invoked = False

    async def fake_invoke(self, question, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal invoked
        invoked = True
        raise AssertionError("a divergent resume must not reach the workflow")

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield object()

    async def fake_ready():  # type: ignore[no-untyped-def]
        return True, ""

    async def prior_state(workflow, thread_id):  # type: ignore[no-untyped-def]
        return {"question": "Is X liable?", "jurisdiction": "us-ca"}

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_state_values", prior_state)

    res = await client.post(
        "/api/analysis",
        json={"thread_id": "thread-x", "use_langgraph": True, **payload},
    )
    assert res.status_code == 409
    body = res.json()
    assert body["thread_id"] == "thread-x"
    assert body["field"] == field
    assert "omit thread_id" in body["detail"]
    assert invoked is False


@pytest.mark.asyncio
async def test_matching_resume_is_allowed_through(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same question in the same jurisdiction resumes normally."""
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import (
        LegalWorkflow,
        LegalWorkflowOutput,
    )

    async def fake_invoke(self, question, **kwargs):  # type: ignore[no-untyped-def]
        return LegalWorkflowOutput(
            answer="a", citations=[], confidence=0.9, langgraph_thread_id="thread-x"
        )

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield object()

    async def fake_ready():  # type: ignore[no-untyped-def]
        return True, ""

    async def prior_state(workflow, thread_id):  # type: ignore[no-untyped-def]
        return {"question": "Is X liable?", "jurisdiction": "us-ca"}

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    monkeypatch.setattr(mod, "_thread_state_values", prior_state)

    res = await client.post(
        "/api/analysis",
        json={
            "text": "Is X liable?",
            "jurisdiction": "us-ca",
            "thread_id": "thread-x",
            "use_langgraph": True,
        },
    )
    assert res.status_code == 200
    assert res.json()["resumed"] is True


@pytest.mark.asyncio
async def test_trace_url_ships_next_to_the_deprecated_spelling(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BL-20260906-10: the deprecation window emits both names, identically.

    `phoenix_trace_url` outlived Phoenix — `core.telemetry.trace_url` is
    backend-agnostic — so `trace_url` is the name going forward. Until no
    client reads the old one, a response that carries either must carry both,
    or a client that switched would silently lose the link.
    """
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import (
        LegalWorkflow,
        LegalWorkflowOutput,
    )

    async def fake_invoke(self, question, **kwargs):  # type: ignore[no-untyped-def]
        return LegalWorkflowOutput(
            answer="a",
            citations=[],
            confidence=0.9,
            langgraph_thread_id="lwf-trace",
            phoenix_trace_url="https://collector.test/traces/abc",
        )

    @asynccontextmanager
    async def fake_saver():  # type: ignore[no-untyped-def]
        yield None

    async def fake_ready():  # type: ignore[no-untyped-def]
        return True, ""

    monkeypatch.setattr(LegalWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)

    res = await client.post("/api/analysis", json={"text": "q"})
    assert res.status_code == 200
    body = res.json()
    assert body["trace_url"] == "https://collector.test/traces/abc"
    assert body["phoenix_trace_url"] == body["trace_url"]
    assert body["irac"]["trace_url"] == body["trace_url"]
    assert body["irac"]["phoenix_trace_url"] == body["trace_url"]


def test_the_new_spelling_backfills_the_old_one() -> None:
    """Mirroring runs both ways, so a `trace_url`-only caller is safe too."""
    from law_ai.agents_runtime.crews.legal_analyst import IRACOutput

    irac = IRACOutput(
        issue="i",
        rule="r",
        application="a",
        conclusion="c",
        confidence=0.5,
        trace_url="https://collector.test/traces/xyz",
    )
    assert irac.phoenix_trace_url == "https://collector.test/traces/xyz"


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
