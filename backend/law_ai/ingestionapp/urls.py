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

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import has_scope, is_signed_in
from law_ai.core.reviewer import attributed, reviewer_from_request
from law_ai.ingestionapp.services import ocrmd_plugin
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


# ---------------------------------------------------------------------------
# The ocrmd plug-in (spec 055): the scanner as a library, on an upload
# ---------------------------------------------------------------------------

_DOC_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TARGET_RE = re.compile(r"^(none|lsat|matter:[a-z0-9][a-z0-9-]{0,63})$")


class OcrmdStatusView(_Base):
    """``GET /api/ingestion/ocrmd/status`` — is the scanner library installed and on,
    where its store is, which OCR engines it found, and which doors this platform opens.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(ocrmd_plugin.status())


class _Refused(Exception):
    """A scan request the door turns away, with the status that says why."""

    def __init__(self, detail: Any, http_status: int) -> None:
        super().__init__(str(detail))
        self.detail = detail
        self.http_status = http_status


class _BadScan(_Refused):
    """A scan request refused before the scanner is touched (a 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status.HTTP_422_UNPROCESSABLE_ENTITY)


def _plugin_gate() -> None:
    """Refuse with a 503 when the embedded scanner is off or absent."""
    if not ocrmd_plugin.enabled():
        raise _Refused(
            "the ocrmd plug-in is off (ENABLE_OCRMD=false)",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not ocrmd_plugin.installed():
        raise _Refused(
            "the ocrmd package is not installed — build the backend image with "
            "INSTALL_OCRMD=1",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _parse_scan_request(
    request: Request,
) -> tuple[Any, str, str, str, dict[str, Any], int]:
    """``(upload, name, doc, target, options, max_pages)`` or :class:`_BadScan`."""
    data: Any = request.data if isinstance(request.data, dict) else {}
    upload = request.FILES.get("file")
    if upload is None:
        raise _BadScan("file is required")
    name = Path(str(getattr(upload, "name", "") or "upload")).name
    if Path(name).suffix.lower() not in ocrmd_plugin.IMAGE_SUFFIXES:
        raise _BadScan(f"unsupported file type {Path(name).suffix!r}")
    doc = str(data.get("doc") or "uploads")
    if not _DOC_SLUG_RE.match(doc):
        raise _BadScan(f"invalid document slug {doc!r}")
    target = str(data.get("target") or "none")
    if not _TARGET_RE.match(target):
        raise _BadScan("target must be none | lsat | matter:<slug>")
    try:
        options = json.loads(str(data.get("options") or "{}"))
    except ValueError as exc:
        raise _BadScan(f"options: {exc}") from exc
    if not isinstance(options, dict):
        raise _BadScan("options must be a JSON object")
    cap = int(getattr(settings, "OCRMD_MAX_PAGES", 5))
    try:
        max_pages = min(int(data.get("max_pages") or cap), cap)
    except ValueError:
        max_pages = cap
    return upload, name, doc, target, options, max_pages


def _owned_matter(request: Request, slug: str) -> Any:
    """The signed-in caller's matter, or a 404 indistinguishable from a stranger's."""
    from law_ai.matters.models import Matter

    owner: Any = request.user
    matter = Matter.objects.filter(
        owner=owner, slug=slug, archived_at__isnull=True
    ).first()
    if matter is None:
        raise Http404("matter not found")
    return matter


def _route_page(
    env: dict[str, Any], target: str, matter: Any, request: Request
) -> dict[str, Any] | None:
    """Hand one envelope to the door ``target`` names; None when there is none."""
    if target == "lsat":
        from law_ai.lsat.services.ocr_intake import IngestScanRequest, ingest_scan

        out = ingest_scan(IngestScanRequest.model_validate(env))
        return {
            "door": "lsat",
            "summary": out.summary,
            "items": out.items,
            "warnings": out.warnings,
        }
    if matter is not None:
        from law_ai.matters.services import scanned

        envelope = ocrmd_plugin.Envelope.model_validate(env)
        artifact, created = scanned.file_page(matter, envelope, request.user)
        return {
            "door": "matter",
            **scanned.delivery(matter, artifact, created, envelope),
        }
    return None


def _page_row(env: dict[str, Any]) -> dict[str, Any]:
    prov: dict[str, Any] = dict(env.get("provenance") or {})
    text = str(env.get("text") or "")
    return {
        "sequence": prov.get("page"),
        "page_id": prov.get("page_id"),
        "status": prov.get("status"),
        "chars": len(text),
        "text": text,
        "provenance": prov,
    }


class OcrmdScanView(_Base):
    """``POST /api/ingestion/ocrmd/scan`` — OCR an uploaded image or PDF here, then route.

    Multipart: ``file``; ``doc`` (the scanner document the pages join, default
    ``uploads``); ``target`` = ``none`` | ``lsat`` | ``matter:<slug>``; ``options`` (JSON,
    the target door's own options); ``max_pages``. Synchronous and bounded by
    ``OCRMD_MAX_PAGES``: the engines take a second or two per page and the caller is a
    person waiting. A whole book goes through a scanner rig posting to the doors, not
    through this one.

    OCR only — see :mod:`law_ai.ingestionapp.services.ocrmd_plugin` for why the embedded
    scanner never calls a model — so every routed page carries a one-reading caveat.
    """

    parser_classes = (MultiPartParser, FormParser)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            return Response(_scan(request))
        except _Refused as exc:
            return Response({"detail": exc.detail}, status=exc.http_status)


def _scan(request: Request) -> dict[str, Any]:
    """The whole upload door; every refusal is a :class:`_Refused`."""
    _plugin_gate()
    upload, name, doc, target, options, max_pages = _parse_scan_request(request)
    matter = None
    if target.startswith("matter:"):
        if not is_signed_in(request):
            raise _Refused(
                "sign in to file a scan on a matter", status.HTTP_401_UNAUTHORIZED
            )
        matter = _owned_matter(request, target[7:])

    with tempfile.TemporaryDirectory(prefix="ocrmd-upload-") as tmp:
        path = Path(tmp) / name
        with path.open("wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        try:
            result = ocrmd_plugin.scan_file(path, doc, max_pages=max_pages)
        except ocrmd_plugin.OcrmdUnavailable as exc:
            raise _Refused(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE) from exc
        except Exception as exc:
            logger.exception("ocrmd scan failed: %s", exc)
            raise _Refused(
                f"scan failed: {type(exc).__name__}",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc

    routed: list[dict[str, Any] | None] = []
    for env in result.pages:
        env["options"] = options
        try:
            routed.append(_route_page(env, target, matter, request))
        except ValidationError as exc:
            raise _Refused(
                exc.errors(include_context=False, include_input=False),
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from exc
    return {
        "document": result.document,
        "engine": result.engine,
        "llm": "none",
        "summary": result.summary(),
        "duplicates": result.duplicates,
        "rejected": result.rejected,
        "unreadable": result.unreadable,
        "pages": [_page_row(env) for env in result.pages],
        "routed": routed,
    }


urlpatterns = [
    path("ocrmd/status", OcrmdStatusView.as_view(), name="ingestion-ocrmd-status"),
    path("ocrmd/scan", OcrmdScanView.as_view(), name="ingestion-ocrmd-scan"),
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
