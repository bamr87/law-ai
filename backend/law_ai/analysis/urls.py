"""Analysis Studio API (spec 007 → spec 011 FR-9 port)."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
from rest_framework import status  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.throttling import (  # type: ignore[import-untyped]
    ScopedRateThrottle,
)
from rest_framework.views import APIView  # type: ignore[import-untyped]

from law_ai.agents_runtime.crews.legal_analyst import IRACOutput, LegalAnalyst
from law_ai.agents_runtime.crews.precedent_hunter import (
    PrecedentHunter,
    PrecedentList,
)
from law_ai.agentsapi.consumers import stream_group
from law_ai.core.auth import RequireAnalysis
from law_ai.core.provenance import provenance

HITL_THRESHOLD = 0.7


class AnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    jurisdiction: str | None = Field(default=None, max_length=64)
    case_id: str | None = Field(default=None, max_length=200)
    # Spec 027: the retrieval-backed LangGraph/Ollama workflow is the DEFAULT
    # engine. Pass false explicitly to reach the dev-time Claude Code path or
    # the honest degraded stub.
    use_langgraph: bool = Field(default=True)
    # Spec 032: client-chosen correlation id. Subscribe to
    # /ws/agents/<stream_id> BEFORE posting, and step events arrive as
    # each agent finishes. Without it the group is keyed on the
    # server-generated analysis id, which the client cannot know until the
    # response arrives — i.e. too late to receive anything.
    stream_id: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"
    )


class AgentTraceEntry(BaseModel):
    agent: str
    trace_id: str | None
    latency_ms: float
    confidence: float


class AnalysisResponse(BaseModel):
    id: str
    timestamp: str
    latency_ms: int
    confidence: float
    requires_human_review: bool
    irac: IRACOutput
    precedents: PrecedentList
    agent_trace: list[AgentTraceEntry]
    phoenix_trace_url: str | None = None
    langgraph_thread_id: str | None = None


_logger = logging.getLogger(__name__)


def _new_analysis_id() -> str:
    return f"an-{secrets.token_hex(6)}"


async def _emit_ws_event(
    stream_key: str,
    payload: dict[str, object],
) -> None:
    """Send a progress event to the ``agent-run-{stream_key}`` WS group.

    ``stream_key`` is the client's ``stream_id`` when supplied, so a client
    that subscribed before posting actually receives these (spec 032).

    Fire-and-forget: if the channel layer is unavailable (no Redis, no
    subscriber), the error is logged but never re-raised so that a Redis
    outage cannot abort an analysis run (spec 021 AC-2, FR-1).
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        await layer.group_send(
            # Shared helper so producer and consumer group names cannot drift.
            stream_group(stream_key),
            {"type": "agent_event", "payload": payload},
        )
        # Transport bookkeeping, not an agent call: a distinct event type
        # keeps agent metrics (latency/confidence/counts) unpolluted.
        provenance.log_event(
            "ws_event_sent",
            {
                "source": "analysis",
                "analysis_id": stream_key,
                "ws_event_type": str(payload.get("type")),
            },
        )
    except Exception:
        _logger.warning(
            "WS event emit failed for stream_key=%s",
            stream_key,
            exc_info=True,
        )


async def _timed[T](awaitable: Awaitable[T]) -> tuple[T, float]:
    """Await *awaitable*, returning ``(result, elapsed_ms)``.

    Lets each agent coroutine report its **own** wall-clock latency instead of
    the combined ``asyncio.gather`` duration (spec 021 §5 FR-2: ``latency_ms``
    in ``agent_step`` / ``AgentTraceEntry`` is per-agent, mirroring
    ``trace_id``/``confidence``).
    """
    start = time.perf_counter()
    result = await awaitable
    return result, (time.perf_counter() - start) * 1000.0


async def _run_analysis(req: AnalysisRequest) -> AnalysisResponse:
    analyst = LegalAnalyst()
    hunter = PrecedentHunter()
    payload: dict[str, str | bool | None] = {
        "text": req.text,
        "jurisdiction": req.jurisdiction,
        "case_id": req.case_id,
        "use_langgraph": req.use_langgraph,
    }
    analysis_id = _new_analysis_id()
    # Events go to the client's stream id when supplied; otherwise the
    # analysis id keeps the old (undeliverable, but harmless) behaviour.
    stream_key = req.stream_id or analysis_id
    started = time.perf_counter()

    async def _run_step(
        agent_name: str, awaitable: Awaitable[Any]
    ) -> tuple[Any, float]:
        """Await one agent and emit its step event *as it finishes*.

        Emitting inside the gather is the point: the previous code awaited
        both agents and only then sent every event, so even a subscribed
        client received the whole trace at once, after the work was done.
        """
        result, elapsed_ms = await _timed(awaitable)
        await _emit_ws_event(
            stream_key,
            {
                "type": "agent_step",
                "agent": agent_name,
                "analysis_id": analysis_id,
                "trace_id": getattr(result, "trace_id", None),
                "latency_ms": round(elapsed_ms, 2),
                "confidence": getattr(result, "confidence", 0.0),
                "degraded": bool(getattr(result, "degraded", False)),
            },
        )
        return result, elapsed_ms

    (irac, analyst_ms), (precedents, hunter_ms) = await asyncio.gather(
        _run_step("LegalAnalyst", analyst.run(payload)),
        _run_step("PrecedentHunter", hunter.run(payload)),
    )
    total_ms = (time.perf_counter() - started) * 1000.0
    # Degraded agents (unimplemented/offline paths) are excluded from the
    # confidence mean — a fabricated-or-empty result must not drag a real
    # agent's score up or down. No real contributions ⇒ confidence 0.0.
    contributions = [
        out.confidence
        for out in (irac, precedents)
        if not getattr(out, "degraded", False)
    ]
    confidence = (
        round(sum(contributions) / len(contributions), 4) if contributions else 0.0
    )
    # Structured flags, not prose string-matching: any degraded agent or an
    # agent-level review flag forces HITL regardless of the confidence mean.
    requires_human_review = (
        confidence < HITL_THRESHOLD
        or irac.degraded
        or precedents.degraded
        or irac.requires_review
    )
    # Step events already fired as each agent finished (see _run_step); this
    # is the terminal event. Fire-and-forget: Redis failure is non-fatal.
    await _emit_ws_event(
        stream_key,
        {
            "type": "complete",
            "analysis_id": analysis_id,
            "confidence": confidence,
            "requires_human_review": requires_human_review,
        },
    )
    irac_sources: list[Any] = list(irac.sources)
    sources: list[dict[str, str]] = [
        {"title": str(s.get("title", "")), "url": str(s.get("url", ""))}
        for s in irac_sources
    ] + [{"title": p.title, "url": p.url} for p in precedents.precedents]
    provenance.log_agent_call(
        agent_name="AnalysisStudio",
        input_data={
            "analysis_id": analysis_id,
            "jurisdiction": req.jurisdiction,
            "case_id": req.case_id,
            "child_trace_ids": [irac.trace_id, precedents.trace_id],
        },
        output_data={
            "confidence": confidence,
            "requires_human_review": requires_human_review,
            "precedent_count": len(precedents.precedents),
        },
        model="multi-agent",
        latency_ms=total_ms,
        confidence=confidence,
        sources=sources,
    )
    trace = [
        AgentTraceEntry(
            agent="LegalAnalyst",
            trace_id=irac.trace_id,
            latency_ms=round(analyst_ms, 2),
            confidence=irac.confidence,
        ),
        AgentTraceEntry(
            agent="PrecedentHunter",
            trace_id=precedents.trace_id,
            latency_ms=round(hunter_ms, 2),
            confidence=precedents.confidence,
        ),
    ]
    return AnalysisResponse(
        id=analysis_id,
        timestamp=datetime.now(UTC).isoformat(),
        latency_ms=int(total_ms),
        confidence=confidence,
        requires_human_review=requires_human_review,
        irac=irac,
        precedents=precedents,
        agent_trace=trace,
        phoenix_trace_url=irac.phoenix_trace_url,
        langgraph_thread_id=irac.langgraph_thread_id,
    )


class AnalysisView(APIView):
    permission_classes = [RequireAnalysis]
    # BL-20260810-11: this endpoint fans out to Ollama (120 s timeout) on an
    # open-by-default auth gate — throttle so one client cannot starve the
    # single local model server for everyone.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            req = AnalysisRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        try:
            body = async_to_sync(_run_analysis)(req)
        except Exception as exc:
            provenance.log_agent_call(
                agent_name="AnalysisStudio",
                input_data={
                    "jurisdiction": req.jurisdiction,
                    "case_id": req.case_id,
                    "use_langgraph": req.use_langgraph,
                    "error": True,
                },
                output_data={
                    "error_class": type(exc).__name__,
                    "error": str(exc)[:500],
                },
                model="multi-agent",
                latency_ms=0.0,
                confidence=0.0,
                sources=[],
            )
            return Response(
                {"detail": f"Analysis failed: {type(exc).__name__}: {str(exc)[:200]}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(body.model_dump())


urlpatterns = [path("", AnalysisView.as_view(), name="analysis-run")]
