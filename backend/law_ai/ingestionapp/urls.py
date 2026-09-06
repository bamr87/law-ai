"""Quarantine review queue API (BL-20260811-01, the UI half of BL-20260810-03).

Spec 029 closed the ingestion HITL loop with two operator surfaces — Django
admin and ``manage.py review_queue`` — both of which require a shell or a
staff account. A domain reviewer who is not an operator still could not work
the queue, so items sat quarantined for want of somebody with a terminal.
This router is the web-app half.

Design constraints it works under:

* **Never writes Neo4j directly.** Approve routes through
  ``services.approval.record_decision`` and ``commit_approved_review``, the
  same audited path admin and the CLI use, so constitution §12 I1 holds and
  the approval → commit handoff stays idempotent.
* **The reviewer is resolved, not claimed** (BL-20260811-04): a signed-in
  account wins over any ``reviewer`` string in the body.
* **Failures are visible.** Approve returns ``committed`` and
  ``commit_error`` rather than reporting a bare success, because an approved
  row whose graph write failed is exactly the state a reviewer must see.

Ids are carried in the query string / body rather than the path:
``PendingReview.id`` is a ``TextField`` that is routinely a source URL
(``https://…/opinion/1/``), which cannot survive a URL path segment.
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import has_scope
from law_ai.core.reviewer import attributed, reviewer_from_request
from law_ai.ingestionapp.services.approval import (
    ApprovalError,
    commit_approved_review,
    record_decision,
    reextract_review,
)

logger = logging.getLogger("law_ai.ingestionapp.api")

#: Its own scope so an instance can hand a reviewer queue access without also
#: handing them the agent key. Falls back to ``AGENT_API_KEY``, and to the
#: local-first open posture when neither is configured — same shape as every
#: other router (``core/auth.py``).
RequireIngestion = has_scope("ingestion", "INGESTION_API_KEY", "AGENT_API_KEY")

#: Query-string ``status`` values and the ORM filter each selects.
STATUS_FILTERS: dict[str, dict[str, Any]] = {
    "pending": {"approved__isnull": True},
    "approved": {"approved": True},
    "rejected": {"approved": False},
    # Approved by a human but not yet in the graph — the state the CLI sweep
    # and the Celery beat are there to drain.
    "awaiting_commit": {"approved": True, "committed_at__isnull": True},
    "committed": {"committed_at__isnull": False},
    # Approved, the commit was attempted, and it failed. Statute rows used to
    # live here permanently (BL-20260811-03); anything here now needs a human.
    "failed": {"approved": True, "committed_at__isnull": True},
}

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class _DecisionRequest(BaseModel):
    """Body of approve/reject/re-extract (``note`` unused by re-extract)."""

    id: str = Field(..., min_length=1)
    reviewer: str = ""
    note: str = ""


def _row(review: Any, *, include_payload: bool = False) -> dict[str, Any]:
    """Serialise one quarantine row for the queue UI."""
    body: dict[str, Any] = {
        "id": review.pk,
        "source": review.source,
        "kind": review.kind,
        "confidence": review.confidence,
        "reason": review.reason or "",
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "approved": review.approved,
        "reviewer": review.reviewer or "",
        "review_note": review.review_note or "",
        "committed_at": (
            review.committed_at.isoformat() if review.committed_at else None
        ),
        "commit_error": review.commit_error or "",
    }
    if include_payload:
        body["payload"] = review.payload
    return body


def _get_review(review_id: str) -> Any:
    from law_ai.ingestionapp.models import PendingReview

    try:
        return PendingReview.objects.get(pk=review_id)
    except PendingReview.DoesNotExist as exc:
        raise Http404("review not found") from exc


class _Base(APIView):
    permission_classes = [RequireIngestion]


class ReviewListView(_Base):
    """``GET /api/ingestion/reviews`` — the queue.

    Payloads are omitted here on purpose: a quarantined opinion carries the
    whole document body, and shipping fifty of them to render a list of fifty
    captions would make the queue unusable. The detail route adds it.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from law_ai.ingestionapp.models import PendingReview

        params = request.query_params
        state = params.get("status") or "pending"
        if state not in STATUS_FILTERS:
            return Response(
                {
                    "detail": f"unknown status {state!r}",
                    "allowed": sorted(STATUS_FILTERS),
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            limit = min(int(params.get("limit") or DEFAULT_LIMIT), MAX_LIMIT)
        except ValueError:
            limit = DEFAULT_LIMIT
        limit = max(limit, 1)

        qs = PendingReview.objects.filter(**STATUS_FILTERS[state])
        if state == "failed":
            qs = qs.exclude(commit_error="")
        if kind := params.get("kind"):
            qs = qs.filter(kind=kind)
        if source := params.get("source"):
            qs = qs.filter(source=source)
        rows = list(qs.order_by("-created_at")[:limit])
        return Response(
            {
                "status": state,
                "reviews": [_row(r) for r in rows],
                "count": len(rows),
                "counts": {
                    name: PendingReview.objects.filter(**flt)
                    .exclude(**({"commit_error": ""} if name == "failed" else {}))
                    .count()
                    for name, flt in STATUS_FILTERS.items()
                },
            }
        )


class ReviewDetailView(_Base):
    """``GET /api/ingestion/reviews/detail?id=…`` — one row, payload included."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        review_id = request.query_params.get("id") or ""
        if not review_id:
            return Response(
                {"detail": "id is required"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(_row(_get_review(review_id), include_payload=True))


class _DecisionView(_Base):
    """Shared body-parsing + attribution for approve and reject."""

    approved: bool = False

    def _decide(self, request: Request) -> tuple[Any, Any] | Response:
        try:
            req = _DecisionRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        review = _get_review(req.id)
        identity = reviewer_from_request(request, claimed=req.reviewer)
        with attributed(identity):
            record_decision(
                review,
                approved=self.approved,
                reviewer=identity.name,
                reviewer_user=identity.user,
                note=req.note,
            )
        return review, identity


class ReviewRejectView(_DecisionView):
    """``POST /api/ingestion/reviews/reject`` — record a rejection + rationale."""

    approved = False

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        outcome = self._decide(request)
        if isinstance(outcome, Response):
            return outcome
        review, _ = outcome
        return Response({"review": _row(review), "committed": False})


class ReviewApproveView(_DecisionView):
    """``POST /api/ingestion/reviews/approve`` — approve, then commit inline.

    The commit is attempted in the same request so the reviewer learns
    immediately whether the graph accepted the item. A commit failure is not
    an API error: the decision is already durably recorded, so the row comes
    back with ``commit_error`` set and the UI shows it.
    """

    approved = True

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        outcome = self._decide(request)
        if isinstance(outcome, Response):
            return outcome
        review, _ = outcome
        try:
            result = async_to_sync(commit_approved_review)(review)
        except ApprovalError as exc:
            logger.warning("approve: commit refused for %s: %s", review.pk, exc)
            result = {"committed": False, "error": str(exc)}
        review.refresh_from_db()
        return Response(
            {
                "review": _row(review),
                "committed": bool(result.get("committed")),
                "edges": result.get("edges", 0),
                "commit_error": review.commit_error or result.get("error") or "",
            }
        )


class ReviewReextractView(_Base):
    """``POST /api/ingestion/reviews/re-extract`` — re-score with today's extractor.

    BL-20260906-04. The third review verb shipped in Django admin and in
    ``manage.py review_queue`` but not here, so a web reviewer could not ask
    the one question that decides most stale rows: "would today's extractor
    still quarantine this?".

    Never commits — even a fresh score that clears the threshold only refreshes
    the row, because constitution §5 makes the human approval the gate.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            req = _DecisionRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        review = _get_review(req.id)
        identity = reviewer_from_request(request, claimed=req.reviewer)
        try:
            with attributed(identity):
                outcome = reextract_review(review, reviewer=identity.name)
        except ApprovalError as exc:
            logger.warning("re-extract refused for %s: %s", review.pk, exc)
            return Response(
                {"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        review.refresh_from_db()
        return Response(
            {
                "review": _row(review),
                "reextracted": bool(outcome.get("reextracted")),
                "previous_confidence": outcome.get("previous_confidence"),
                "confidence": outcome.get("confidence"),
                "clears_threshold": bool(outcome.get("clears_threshold")),
                "n_citations": outcome.get("n_citations", 0),
                "error": outcome.get("error", ""),
                "skipped": outcome.get("skipped", ""),
            }
        )


urlpatterns = [
    path("reviews", ReviewListView.as_view(), name="ingestion-reviews"),
    path("reviews/detail", ReviewDetailView.as_view(), name="ingestion-review-detail"),
    path(
        "reviews/approve", ReviewApproveView.as_view(), name="ingestion-review-approve"
    ),
    path("reviews/reject", ReviewRejectView.as_view(), name="ingestion-review-reject"),
    path(
        "reviews/re-extract",
        ReviewReextractView.as_view(),
        name="ingestion-review-reextract",
    ),
]
