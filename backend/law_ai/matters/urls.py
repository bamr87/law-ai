"""Matter workspace API (spec 036 T-001/T-003, BL-20260817-01/02).

Every route here is owner-scoped and requires a real signed-in account: a
matter holds client facts, so an API key with a broad scope is not a
sufficient credential and an anonymous local instance simply has no matters.

The lookup discipline is the same in every view and is the point of
:func:`_matter_or_404`: the URL carries a *slug*, the queryset is filtered by
``owner=request.user``, and a slug that belongs to someone else is a plain
404 — identical to one that never existed, so probing learns nothing
(BL-20260830-08's IDOR trap).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from django.db import IntegrityError
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import is_signed_in
from law_ai.core.provenance import provenance
from law_ai.matters.models import (
    SLUG_RE,
    Matter,
    MatterArtifact,
    MatterAuthority,
    MatterTask,
)

logger = logging.getLogger("law_ai.matters")


class _Base(APIView):
    """Signed-in only. Never an API key: matters are per-account data."""

    permission_classes = [AllowAny]

    def initial(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if not is_signed_in(request):
            from rest_framework.exceptions import NotAuthenticated

            raise NotAuthenticated("sign in to use matters")


def _matter_or_404(request: Any, slug: str) -> Matter:
    matter = Matter.objects.filter(
        owner=request.user, slug=slug, archived_at__isnull=True
    ).first()
    if matter is None:
        raise Http404("matter not found")
    return matter


def _slugify(name: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    while "--" in base:
        base = base.replace("--", "-")
    return (base or "matter")[:64]


class _MatterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    description: str = ""
    issue_tags: list[str] = Field(default_factory=list)
    jurisdiction: str = ""
    stage: str = Matter.STAGE_INTAKE


class _MatterPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    issue_tags: list[str] | None = None
    jurisdiction: str | None = None
    stage: str | None = None
    archived: bool | None = None


class MatterListView(_Base):
    """``GET /api/matters`` list · ``POST /api/matters`` create."""

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        rows = Matter.objects.filter(owner=request.user, archived_at__isnull=True)
        return Response({"matters": [m.as_row() for m in rows], "count": rows.count()})

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        try:
            req = _MatterCreateRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        slug = (req.slug or _slugify(req.name)).strip().lower()
        if not SLUG_RE.match(slug):
            return Response(
                {"detail": f"invalid slug {slug!r}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if req.stage not in Matter.STAGES:
            return Response(
                {"detail": f"unknown stage {req.stage!r}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            matter = Matter.objects.create(
                owner=request.user,
                slug=slug,
                name=req.name,
                description=req.description,
                issue_tags=list(req.issue_tags),
                jurisdiction=req.jurisdiction,
                stage=req.stage,
            )
        except IntegrityError:
            return Response(
                {"detail": f"you already have a matter at {slug!r}"},
                status=status.HTTP_409_CONFLICT,
            )
        provenance.log_event(
            "matter.created",
            {"matter_id": matter.pk, "slug": slug, "stage": matter.stage},
        )
        return Response(matter.as_payload(), status=status.HTTP_201_CREATED)


class MatterDetailView(_Base):
    """``GET/PATCH /api/matters/<slug>`` — read or update one owned matter."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        body = matter.as_payload()
        body["artifacts"] = [
            a.as_payload() for a in matter.artifacts.filter(archived_at__isnull=True)
        ]
        body["authorities"] = [
            a.as_payload() for a in matter.authorities.filter(archived_at__isnull=True)
        ]
        body["tasks"] = [
            t.as_payload() for t in matter.tasks.filter(archived_at__isnull=True)
        ]
        return Response(body)

    def patch(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        try:
            req = _MatterPatchRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.stage is not None and req.stage not in Matter.STAGES:
            return Response(
                {"detail": f"unknown stage {req.stage!r}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        for field in ("name", "description", "jurisdiction", "stage"):
            value = getattr(req, field)
            if value is not None:
                setattr(matter, field, value)
        if req.issue_tags is not None:
            matter.issue_tags = list(req.issue_tags)
        if req.archived:
            # Soft delete only (§5): the row stays, the API stops serving it.
            matter.archived_at = datetime.now(UTC)
        matter.save()
        provenance.log_event(
            "matter.updated",
            {"matter_id": matter.pk, "slug": matter.slug, "archived": req.archived},
        )
        return Response(matter.as_payload())


class _ArtifactRequest(BaseModel):
    kind: str = MatterArtifact.KIND_NOTE
    title: str = ""
    body: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ""
    analysis_id: str = ""
    source: str = ""
    confidence: float = 0.0


class MatterArtifactListView(_Base):
    """``GET/POST /api/matters/<slug>/artifacts``."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        rows = matter.artifacts.filter(archived_at__isnull=True)
        return Response({"artifacts": [a.as_payload() for a in rows]})

    def post(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        try:
            req = _ArtifactRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.kind not in MatterArtifact.KINDS:
            return Response(
                {"detail": f"unknown artifact kind {req.kind!r}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        artifact = MatterArtifact.objects.create(
            matter=matter,
            kind=req.kind,
            title=req.title,
            body=req.body,
            trace_id=req.trace_id,
            analysis_id=req.analysis_id,
            source=req.source,
            confidence=req.confidence,
            created_by=request.user,
        )
        provenance.log_event(
            "matter.artifact_added",
            {
                "matter_id": matter.pk,
                "artifact_id": artifact.pk,
                "kind": artifact.kind,
                "trace_id": artifact.trace_id,
            },
        )
        return Response(artifact.as_payload(), status=status.HTTP_201_CREATED)


class _AuthorityRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    node_label: str = "Case"
    citation: str = ""
    title: str = ""
    note: str = ""
    source: str = ""
    confidence: float = 0.0
    verified: bool = False


class MatterAuthorityListView(_Base):
    """``GET/POST /api/matters/<slug>/authorities`` — the matter's cited law."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        rows = matter.authorities.filter(archived_at__isnull=True)
        return Response({"authorities": [a.as_payload() for a in rows]})

    def post(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        try:
            req = _AuthorityRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        now = datetime.now(UTC)
        authority, created = MatterAuthority.objects.update_or_create(
            matter=matter,
            node_id=req.node_id,
            defaults={
                "node_label": req.node_label,
                "citation": req.citation,
                "title": req.title,
                "note": req.note,
                "source": req.source,
                "confidence": req.confidence,
                "archived_at": None,
                # Verification is a human act (§5), so it is recorded with the
                # account that performed it, never inferred.
                "verified_at": now if req.verified else None,
                "verified_by": request.user if req.verified else None,
            },
        )
        provenance.log_event(
            "matter.authority_recorded",
            {
                "matter_id": matter.pk,
                "node_id": authority.node_id,
                "verified": authority.is_verified,
                "created": created,
            },
        )
        return Response(
            authority.as_payload(),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class _TaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = ""
    due_at: datetime | None = None
    source_artifact_id: int | None = None


class _TaskPatchRequest(BaseModel):
    title: str | None = None
    detail: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    archived: bool | None = None


class MatterTaskListView(_Base):
    """``GET/POST /api/matters/<slug>/tasks`` — the action stage's to-do list."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        rows = matter.tasks.filter(archived_at__isnull=True)
        state = request.query_params.get("status")
        if state:
            rows = rows.filter(status=state)
        return Response({"tasks": [t.as_payload() for t in rows]})

    def post(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        matter = _matter_or_404(request, slug)
        try:
            req = _TaskRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        source = None
        if req.source_artifact_id is not None:
            source = MatterArtifact.objects.filter(
                matter=matter, pk=req.source_artifact_id
            ).first()
            if source is None:
                return Response(
                    {"detail": "source artifact is not in this matter"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        task = MatterTask.objects.create(
            matter=matter,
            title=req.title,
            detail=req.detail,
            due_at=req.due_at,
            source_artifact=source,
            created_by=request.user,
        )
        provenance.log_event(
            "matter.task_created",
            {
                "matter_id": matter.pk,
                "task_id": task.pk,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            },
        )
        return Response(task.as_payload(), status=status.HTTP_201_CREATED)


class MatterTaskDetailView(_Base):
    """``PATCH /api/matters/<slug>/tasks/<id>`` — complete, reschedule, archive."""

    def patch(
        self, request: Any, slug: str, task_id: int, *args: Any, **kwargs: Any
    ) -> Response:
        matter = _matter_or_404(request, slug)
        task = MatterTask.objects.filter(matter=matter, pk=task_id).first()
        if task is None:
            raise Http404("task not found")
        try:
            req = _TaskPatchRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.status is not None and req.status not in MatterTask.STATUSES:
            return Response(
                {"detail": f"unknown status {req.status!r}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if req.title is not None:
            task.title = req.title
        if req.detail is not None:
            task.detail = req.detail
        if req.due_at is not None:
            task.due_at = req.due_at
            # A rescheduled task deserves its reminder again.
            task.reminded_at = None
        if req.status is not None:
            task.status = req.status
            task.completed_at = (
                datetime.now(UTC) if req.status == MatterTask.STATUS_DONE else None
            )
        if req.archived:
            task.archived_at = datetime.now(UTC)
        task.save()
        return Response(task.as_payload())


class MatterCalendarView(_Base):
    """``GET /api/matters/calendar`` — every open dated task the caller owns.

    The per-matter list answers "what is left here"; a practitioner works
    several matters at once and needs the other question — "what is due this
    week, anywhere" — which no per-matter route can answer.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        from law_ai.matters.services.tasks import calendar_for_user

        try:
            days = int(request.query_params.get("days", "30"))
        except ValueError:
            days = 30
        return Response(calendar_for_user(request.user, days=max(1, min(days, 365))))


class MatterExportView(_Base):
    """``GET /api/matters/<slug>/export`` — the portability bundle."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        from law_ai.matters.services.export import export_matter

        matter = _matter_or_404(request, slug)
        bundle = export_matter(matter)
        response = Response(bundle)
        response["Content-Disposition"] = (
            f'attachment; filename="matter-{matter.slug}.json"'
        )
        return response


class MatterMemoView(_Base):
    """``GET /api/matters/<slug>/memo`` — a deterministic draft memo.

    BL-20260817-03, first half. The memo is *composed*, not generated: it
    arranges the artifacts already filed under the matter, formats the
    authorities per Bluebook, and carries a provenance footer listing the
    trace id behind each section. DOCX/PDF rendering is the remaining half and
    needs runtime dependencies this image does not carry.
    """

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        from law_ai.matters.drafting.memo import compose_memo

        matter = _matter_or_404(request, slug)
        # `output`, not `format`: DRF reserves the `format` query param for
        # renderer selection and 404s on a value it does not know.
        wanted = (request.query_params.get("output") or "markdown").lower()
        if wanted not in {"markdown", "md"}:
            return Response(
                {
                    "detail": (
                        f"format {wanted!r} is not available yet; DOCX/PDF "
                        "rendering is pending (BL-20260817-03)"
                    )
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        memo = compose_memo(matter)
        provenance.log_event(
            "matter.memo_composed",
            {
                "matter_id": matter.pk,
                "slug": matter.slug,
                "artifacts": memo["artifact_count"],
                "authorities": memo["authority_count"],
            },
        )
        return Response(memo)


class MatterStudyPlanView(_Base):
    """``GET /api/matters/<slug>/study-plan`` — doctrine gaps → LSAT material."""

    def get(self, request: Any, slug: str, *args: Any, **kwargs: Any) -> Response:
        from law_ai.lsat.services.doctrine_map import study_plan_for_matter

        matter = _matter_or_404(request, slug)
        return Response(study_plan_for_matter(matter, user=request.user))


urlpatterns = [
    path("", MatterListView.as_view(), name="matter-list"),
    path("calendar", MatterCalendarView.as_view(), name="matter-calendar"),
    path("<str:slug>", MatterDetailView.as_view(), name="matter-detail"),
    path(
        "<str:slug>/artifacts",
        MatterArtifactListView.as_view(),
        name="matter-artifacts",
    ),
    path(
        "<str:slug>/authorities",
        MatterAuthorityListView.as_view(),
        name="matter-authorities",
    ),
    path("<str:slug>/tasks", MatterTaskListView.as_view(), name="matter-tasks"),
    path(
        "<str:slug>/tasks/<int:task_id>",
        MatterTaskDetailView.as_view(),
        name="matter-task-detail",
    ),
    path("<str:slug>/export", MatterExportView.as_view(), name="matter-export"),
    path("<str:slug>/memo", MatterMemoView.as_view(), name="matter-memo"),
    path(
        "<str:slug>/study-plan",
        MatterStudyPlanView.as_view(),
        name="matter-study-plan",
    ),
]
