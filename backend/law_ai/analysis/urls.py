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
from rest_framework.views import APIView  # type: ignore[import-untyped]

from law_ai.agents_runtime.crews.legal_analyst import IRACOutput, LegalAnalyst
from law_ai.agents_runtime.crews.precedent_hunter import (
    PrecedentHunter,
    PrecedentList,
)
from law_ai.core.auth import RequireAnalysis
from law_ai.core.provenance import provenance

HITL_THRESHOLD = 0.7


class AnalysisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    jurisdiction: str | None = Field(default=None, max_length=64)
    case_id: str | None = Field(default=None, max_length=200)
    use_langgraph: bool = Field(default=False)


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
    analysis_id: str,
    payload: dict[str, object],
) -> None:
    """Send a progress event to the ``agent-run-{analysis_id}`` WS group.

    Fire-and-forget: if the channel layer is unavailable (no Redis, no
    subscriber), the error is logged but never re-raised so that a Redis
    outage cannot abort an analysis run (spec 021 AC-2, FR-1).
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        await layer.group_send(
            f"agent-run-{analysis_id}",
            {"type": "agent_event", "payload": payload},
        )
        provenance.log_agent_call(  # type: ignore[no-untyped-call]
            agent_name="AnalysisStudio",
            input_data={
                "event_type": "ws_event_sent",
                "source": "analysis",
                "analysis_id": analysis_id,
                "ws_event_type": str(payload.get("type")),
            },
            output_data={},
            model="channels",
            latency_ms=0.0,
            confidence=1.0,
        )
    except Exception:
        _logger.warning(
            "WS event emit failed for analysis_id=%s",
            analysis_id,
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
    started = time.perf_counter()
    (irac, analyst_ms), (precedents, hunter_ms) = await asyncio.gather(
        _timed(analyst.run(payload)),  # type: ignore[no-untyped-call]
        _timed(hunter.run(payload)),  # type: ignore[no-untyped-call]
    )
    total_ms = (time.perf_counter() - started) * 1000.0
    confidence = round((irac.confidence + precedents.confidence) / 2, 4)
    requires_human_review = confidence < HITL_THRESHOLD or "Pending human review" in (
        irac.conclusion or ""
    )
    # Emit WS step events — fire-and-forget. Redis failure is non-fatal (AC-2).
    await _emit_ws_event(
        analysis_id,
        {
            "type": "agent_step",
            "agent": "LegalAnalyst",
            "trace_id": irac.trace_id,
            "latency_ms": round(analyst_ms, 2),
            "confidence": irac.confidence,
        },
    )
    await _emit_ws_event(
        analysis_id,
        {
            "type": "agent_step",
            "agent": "PrecedentHunter",
            "trace_id": precedents.trace_id,
            "latency_ms": round(hunter_ms, 2),
            "confidence": precedents.confidence,
        },
    )
    await _emit_ws_event(
        analysis_id,
        {
            "type": "complete",
            "analysis_id": analysis_id,
            "confidence": confidence,
            "requires_human_review": requires_human_review,
        },
    )
    irac_sources: list[Any] = list(irac.sources)  # type: ignore[no-untyped-call]
    sources: list[dict[str, str]] = [
        {"title": str(s.get("title", "")), "url": str(s.get("url", ""))}
        for s in irac_sources
    ] + [{"title": p.title, "url": p.url} for p in precedents.precedents]
    provenance.log_agent_call(  # type: ignore[no-untyped-call]
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
            provenance.log_agent_call(  # type: ignore[no-untyped-call]
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
