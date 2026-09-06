"""Analysis Studio API (spec 007 → spec 011 FR-9 port)."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import (
    settings as django_settings,
)
from django.utils import timezone
from django.urls import path
from pydantic import BaseModel, Field, PrivateAttr, ValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.agents_runtime.crews.legal_analyst import IRACOutput, LegalAnalyst
from law_ai.agents_runtime.crews.precedent_hunter import (
    PrecedentHunter,
    PrecedentList,
)
from law_ai.agentsapi.streaming import emit_stream_event
from law_ai.core.auth import RequireAnalysis, is_signed_in
from law_ai.core.provenance import provenance
from law_ai.core.throttling import ScopedActorRateThrottle

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
    # BL-20260810-13: durable LangGraph thread. Pass the
    # `langgraph_thread_id` from a previous response to resume that thread's
    # checkpointed state instead of starting a fresh one. Same charset/length
    # rule as stream_id — it becomes a checkpointer key.
    thread_id: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"
    )
    # BL-20260817-05: the matter this research round belongs to. When present
    # (and owned by the caller — `AnalysisView.post` checks), GraphRAG promotes
    # the authorities that matter has already had verified, so a later round
    # ranks known-good citations first. The bias is reported back in
    # `retrieval_stats.boosted_count` / `boost_source`.
    matter_id: int | None = Field(default=None, ge=1)


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
    resumed: bool = Field(
        default=False,
        description=(
            "True when the requested thread_id already held checkpointed "
            "state and this run continued it (BL-20260810-13)."
        ),
    )
    # BL-20260429-25: the parent AnalysisStudio provenance trace, carried out
    # of the async run so the sync view can persist it. Private, so the wire
    # shape (and the exported API schema) is unchanged.
    _parent_trace_id: str = PrivateAttr(default="")


_logger = logging.getLogger(__name__)


def _new_analysis_id() -> str:
    return f"an-{secrets.token_hex(6)}"


async def _emit_ws_event(
    stream_key: str,
    payload: dict[str, object],
) -> None:
    """Send a progress event to the ``agent-run-{stream_key}`` WS group.

    Thin alias over :func:`law_ai.agentsapi.streaming.emit_stream_event`, which
    is where this logic now lives so the LSAT tutor and the autonomy cycle can
    stream progress through the same helper (BL-20260811-15). The
    fire-and-forget guarantee is unchanged: a Redis outage cannot abort an
    analysis run (spec 021 AC-2, FR-1).
    """
    await emit_stream_event(stream_key, dict(payload), source="analysis")


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
    analysis_id = _new_analysis_id()
    payload: dict[str, str | bool | int | None] = {
        "text": req.text,
        "jurisdiction": req.jurisdiction,
        "case_id": req.case_id,
        "use_langgraph": req.use_langgraph,
        "thread_id": req.thread_id,
        # BL-20260817-05: reaches LegalWorkflow.invoke(matter_id=...) and from
        # there the retriever's boost set. Ownership is proved before we get
        # here.
        "matter_id": req.matter_id,
        # BL-20260905-11: with a stream id the analyst relays its deltas to
        # this run's group while it generates, so the 56-103s IRAC wait is
        # visible instead of blank.
        "stream_id": req.stream_id,
        "analysis_id": analysis_id,
    }
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
        # §13: a precedent emitted without a complete issuing authority is a
        # statement of law nobody has vouched for (BL-20260803-04).
        or precedents.requires_review
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
    parent_trace_id = provenance.log_agent_call(
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
    response = AnalysisResponse(
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
        resumed=bool(getattr(irac, "resumed", False)),
    )
    response._parent_trace_id = parent_trace_id
    return response


_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

#: Re-exported so the thread endpoint and the analysis path share one
#: saver lifecycle (and one monkeypatch point in tests).
from law_ai.agents_runtime.crews.legal_analyst import (  # noqa: E402
    _analysis_checkpointer,
)


async def _thread_snapshot(thread_id: str) -> dict[str, Any]:
    """Summarise a checkpointed LangGraph thread for the resume UI.

    Opens a saver for the read and closes it again — same per-request
    lifecycle as the analysis path, for the same event-loop reason.
    """
    from law_ai.agents_runtime.graphs import LegalWorkflow

    async with _analysis_checkpointer() as saver:
        if saver is None:
            return {
                "thread_id": thread_id,
                "exists": False,
                "detail": "no checkpointer configured",
            }
        workflow = LegalWorkflow(checkpointer=saver)
        snapshot = await workflow.get_state(thread_id)

    values = getattr(snapshot, "values", None) or {}
    if not values:
        return {"thread_id": thread_id, "exists": False}
    return {
        "thread_id": thread_id,
        "exists": True,
        "question": str(values.get("question") or "")[:500],
        "jurisdiction": values.get("jurisdiction"),
        "case_id": values.get("case_id"),
        "retrieved_count": len(values.get("retrieved") or []),
        "citation_count": len(values.get("citations") or []),
    }


def _persist_run(req: AnalysisRequest, body: AnalysisResponse, request: Any) -> None:
    """Store a finished run so it can be revisited (BL-20260429-25).

    Best-effort by construction: an analysis that already ran and answered
    must not turn into a 500 because Postgres blinked, so every failure is
    logged and swallowed. The JSONL provenance trail is unaffected either way.
    """
    from law_ai.analysis.models import AnalysisRun

    try:
        AnalysisRun.objects.update_or_create(
            analysis_id=body.id,
            defaults={
                "request": req.model_dump(),
                "response": body.model_dump(),
                "trace_id": body._parent_trace_id or "",
                "child_trace_ids": [
                    entry.trace_id for entry in body.agent_trace if entry.trace_id
                ],
                "engine": (
                    AnalysisRun.ENGINE_LANGGRAPH
                    if req.use_langgraph
                    else AnalysisRun.ENGINE_DIRECT
                ),
                "confidence": body.confidence,
                "requires_human_review": body.requires_human_review,
                "created_by": request.user if is_signed_in(request) else None,
                # NFR-PRIV-1: a deployment that handles confidential matters
                # sets ANALYSIS_SHAREABLE_DEFAULT=false and no run can ever
                # be given a public slug.
                "shareable": bool(
                    getattr(django_settings, "ANALYSIS_SHAREABLE_DEFAULT", True)
                ),
            },
        )
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch
        _logger.warning(
            "analysis %s not persisted (%s): %s", body.id, type(exc).__name__, exc
        )


def _reject_unowned_matter(request: Any, matter_id: int | None) -> Any | None:
    """Guard the BL-20260817-05 boost against being aimed at someone else's matter.

    The boost set is a matter's *verified* authorities, so honouring an
    arbitrary id would leak — through the ranking, and through
    ``retrieval_stats.boost_source`` — which authorities another account has
    checked. Ownership is therefore proved here, before the id reaches the
    workflow, and an id the caller does not own answers 404 exactly as
    ``/api/matters/<slug>`` does: indistinguishable from one that never
    existed. Returns a ``Response`` to send, or ``None`` to proceed.
    """
    if not matter_id:
        return None
    if not is_signed_in(request):
        return Response(
            {"detail": "sign in to scope an analysis to a matter"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    from law_ai.matters.models import Matter

    owned = Matter.objects.filter(
        pk=matter_id, owner=request.user, archived_at__isnull=True
    ).exists()
    if not owned:
        return Response(
            {"detail": "matter not found"}, status=status.HTTP_404_NOT_FOUND
        )
    return None


class AnalysisView(APIView):
    permission_classes = [RequireAnalysis]
    # BL-20260810-11: this endpoint fans out to Ollama (120 s timeout) on an
    # open-by-default auth gate — throttle so one client cannot starve the
    # single local model server for everyone.
    # Bucketed per API token / per signed-in user, falling back to IP
    # (BL-20260811-06, BL-20260503-12) — a shared proxy no longer makes one
    # user's burst everyone else's 429.
    throttle_classes = [ScopedActorRateThrottle]
    throttle_scope = "llm"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            req = AnalysisRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        denied = _reject_unowned_matter(request, req.matter_id)
        if denied is not None:
            return denied
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
        _persist_run(req, body, request)
        return Response(body.model_dump())


class AnalysisThreadView(APIView):
    """``GET /api/analysis/threads/<thread_id>`` — inspect a LangGraph thread.

    BL-20260810-13: lets the UI tell "this thread has state to resume" from
    "this id has never been seen". Returns the persisted question/jurisdiction
    and the node checkpoint count, never the full state blob — a checkpoint
    can carry every retrieved passage, which is not what a resume banner
    needs.
    """

    permission_classes = [RequireAnalysis]

    def get(self, request: Any, thread_id: str, *args: Any, **kwargs: Any) -> Any:
        if not _THREAD_ID_RE.match(thread_id or ""):
            return Response(
                {"detail": "invalid thread_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            snapshot = async_to_sync(_thread_snapshot)(thread_id)
        except Exception as exc:  # never 500 on a read-only probe
            _logger.warning("thread lookup failed for %s: %s", thread_id, exc)
            return Response(
                {
                    "thread_id": thread_id,
                    "exists": False,
                    "detail": f"checkpointer unavailable: {type(exc).__name__}",
                }
            )
        return Response(snapshot)


class AnalysisDetailView(APIView):
    """``GET /api/analysis/<analysis_id>`` — revisit a persisted run.

    Read-only and cheap (no model call), so it carries the ``analysis`` scope
    gate but no LLM throttle. An archived run is a 404: soft-deleted means
    gone as far as the API is concerned (constitution §5).
    """

    permission_classes = [RequireAnalysis]

    def get(self, request: Any, analysis_id: str, *args: Any, **kwargs: Any) -> Any:
        from law_ai.analysis.models import AnalysisRun

        try:
            run = AnalysisRun.objects.get(
                analysis_id=analysis_id, archived_at__isnull=True
            )
        except AnalysisRun.DoesNotExist:
            return Response(
                {"detail": f"analysis {analysis_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        provenance.log_event(
            "analysis_replayed",
            {"source": "analysis", "analysis_id": analysis_id},
        )
        return Response(run.as_payload())


# ---------------------------------------------------------------------------
# Save & share (BL-20260429-26 / spec 036 T-007)
# ---------------------------------------------------------------------------
def _run_for_share(analysis_id: str) -> Any:
    from law_ai.analysis.models import AnalysisRun

    return AnalysisRun.objects.filter(
        analysis_id=analysis_id, archived_at__isnull=True
    ).first()


def _shareable_run_or_refusal(request: Any, analysis_id: str) -> tuple[Any, Any]:
    """Resolve the run a mint request targets, or the reason it is refused.

    Returns ``(run, None)`` when minting may proceed and ``(None, Response)``
    otherwise. Split out of the view so the guard chain does not bury the one
    interesting line (ruff PLR0911).
    """
    if not is_signed_in(request):
        return None, Response(
            {"detail": "sign in to share an analysis"},
            status=status.HTTP_403_FORBIDDEN,
        )
    run = _run_for_share(analysis_id)
    if run is None:
        return None, Response(
            {"detail": f"analysis {analysis_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    is_staff = bool(getattr(request.user, "is_staff", False))
    if run.created_by_id not in (None, request.user.pk) and not is_staff:
        return None, Response(
            {"detail": "not your analysis to share"},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not run.shareable:
        return None, Response(
            {"detail": "this analysis is marked not shareable"},
            status=status.HTTP_403_FORBIDDEN,
        )
    return run, None


class AnalysisShareView(APIView):
    """Mint (POST) or list (GET) the share links of one analysis.

    Minting is for signed-in users only: an anonymous key-only caller has no
    identity to attribute a public link to, and "who published this" is the
    one question a share link must always be able to answer.
    """

    permission_classes = [RequireAnalysis]

    def get(self, request: Any, analysis_id: str, *args: Any, **kwargs: Any) -> Any:
        # Listing exposes *live slugs*, which are credentials — so it needs the
        # same identity minting does, not just the deployment's scope key.
        if not is_signed_in(request):
            return Response(
                {"detail": "sign in to list share links"},
                status=status.HTTP_403_FORBIDDEN,
            )
        run = _run_for_share(analysis_id)
        if run is None:
            return Response(
                {"detail": f"analysis {analysis_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        links = [link.as_payload() for link in run.share_links.all()]
        return Response({"analysis_id": analysis_id, "links": links})

    def post(self, request: Any, analysis_id: str, *args: Any, **kwargs: Any) -> Any:
        from law_ai.analysis.models import SLUG_RE, ShareLink

        run, refusal = _shareable_run_or_refusal(request, analysis_id)
        if refusal is not None:
            return refusal

        data = request.data if isinstance(request.data, dict) else {}
        raw_slug = str(data.get("slug") or "").strip().lower()
        if raw_slug and not SLUG_RE.match(raw_slug):
            return Response(
                {
                    "detail": (
                        "slug must be 3-64 chars of a-z, 0-9, - or _ and start "
                        "with a letter or digit"
                    )
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        slug = raw_slug or ShareLink.mint_slug()
        if ShareLink.objects.filter(slug=slug).exists():
            # Revoked slugs stay taken, so a dead link can never be revived
            # under a new owner.
            return Response(
                {"detail": f"slug {slug!r} is taken"},
                status=status.HTTP_409_CONFLICT,
            )
        link = ShareLink.objects.create(
            slug=slug,
            analysis=run,
            label=str(data.get("label") or "")[:200],
            created_by=request.user,
        )
        provenance.log_event(
            "share_link.minted",
            {
                "source": "analysis",
                "analysis_id": analysis_id,
                "slug": slug,
                "actor": request.user.get_username(),
            },
        )
        return Response(link.as_payload(), status=status.HTTP_201_CREATED)


class AnalysisShareRevokeView(APIView):
    """``DELETE /api/analysis/<id>/share/<slug>`` — revoke one link."""

    permission_classes = [RequireAnalysis]

    def delete(
        self, request: Any, analysis_id: str, slug: str, *args: Any, **kwargs: Any
    ) -> Any:
        from law_ai.analysis.models import ShareLink

        if not is_signed_in(request):
            return Response(
                {"detail": "sign in to revoke a share link"},
                status=status.HTTP_403_FORBIDDEN,
            )
        link = ShareLink.objects.filter(
            slug=slug, analysis_id=analysis_id, revoked_at__isnull=True
        ).first()
        if link is None:
            return Response(
                {"detail": f"share link {slug} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if link.created_by_id not in (None, request.user.pk) and not getattr(
            request.user, "is_staff", False
        ):
            return Response(
                {"detail": "not your link to revoke"},
                status=status.HTTP_403_FORBIDDEN,
            )
        link.revoked_at = timezone.now()
        link.save(update_fields=["revoked_at"])
        provenance.log_event(
            "share_link.revoked",
            {
                "source": "analysis",
                "analysis_id": analysis_id,
                "slug": slug,
                "actor": request.user.get_username(),
            },
        )
        return Response(link.as_payload())


urlpatterns = [
    path("", AnalysisView.as_view(), name="analysis-run"),
    path(
        "threads/<str:thread_id>",
        AnalysisThreadView.as_view(),
        name="analysis-thread",
    ),
    path(
        "<str:analysis_id>/share",
        AnalysisShareView.as_view(),
        name="analysis-share",
    ),
    path(
        "<str:analysis_id>/share/<str:slug>",
        AnalysisShareRevokeView.as_view(),
        name="analysis-share-revoke",
    ),
    # Last: a bare segment would otherwise shadow "threads/...".
    path(
        "<str:analysis_id>",
        AnalysisDetailView.as_view(),
        name="analysis-detail",
    ),
]
