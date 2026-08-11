"""Approval → commit path for quarantined documents (spec 029, BL-20260810-03).

Before this module, ``PendingReview.approved`` had **no consumer**: a human
could flip it in Django admin and nothing happened — approved knowledge
never reached Neo4j, so the corpus could not grow through the sanctioned
HITL path. This closes that loop.

Invariants
----------
- **§12 I1** — graph writes go through ``IngestionScout.run_and_commit``
  (with ``force_commit=True``, because the human approval *is* the gate);
  this module never touches Neo4j directly.
- **§4** — every decision and every commit emits a provenance event, and
  the outcome is persisted on the row (``committed_at`` / ``commit_error``)
  so a failed graph write is visible rather than silently "approved".
- **Idempotent** — an already-committed row is skipped, so re-running the
  sweep (Celery beat, CLI, admin action) cannot double-write.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync

from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.ingestionapp.approval")

#: Cap on rows processed per sweep so a large backlog cannot monopolise a
#: worker; the next tick picks up where this one stopped.
DEFAULT_SWEEP_LIMIT = 25


class ApprovalError(RuntimeError):
    """Raised when a review cannot be committed (wrong state, bad payload)."""


def record_decision(
    review: Any,
    *,
    approved: bool,
    reviewer: str = "",
    note: str = "",
) -> None:
    """Persist a human review decision with its author and rationale (§4).

    Does **not** commit — approval and commit are separate steps so a graph
    outage cannot silently discard a reviewer's decision.
    """
    review.approved = approved
    review.reviewed_at = datetime.now(UTC)
    review.reviewer = reviewer or ""
    review.review_note = note or ""
    review.save(update_fields=["approved", "reviewed_at", "reviewer", "review_note"])
    provenance.log_event(
        "quarantine_decision",
        {
            "review_id": review.pk,
            "source": review.source,
            "kind": review.kind,
            "approved": approved,
            "reviewer": reviewer or "(unattributed)",
            "note": (note or "")[:500],
            "confidence": review.confidence,
        },
    )


def _extraction_payload(review: Any) -> dict[str, Any]:
    """Recover the original document payload from a quarantine row.

    ``quarantine_extraction`` stores the task envelope
    (``{id, source, confidence, reason, payload}``); older spec-004 rows
    stored the document directly. Accept both.
    """
    stored = review.payload or {}
    if isinstance(stored, dict) and isinstance(stored.get("payload"), dict):
        return dict(stored["payload"])
    if isinstance(stored, dict):
        return dict(stored)
    raise ApprovalError(f"review {review.pk} has an unusable payload")


async def commit_approved_review(review: Any) -> dict[str, Any]:
    """Commit one approved quarantine row to the knowledge graph.

    Returns a summary dict. Never raises for an ordinary graph failure —
    the error is recorded on the row and surfaced in the return value so a
    sweep can continue with the remaining rows.
    """
    from asgiref.sync import sync_to_async

    if review.approved is not True:
        raise ApprovalError(
            f"review {review.pk} is not approved (approved={review.approved!r})"
        )
    if review.committed_at is not None:
        return {
            "id": review.pk,
            "committed": False,
            "skipped": "already-committed",
            "edges": 0,
        }

    from law_ai.ingestionapp.services.scout import IngestionScout

    payload = _extraction_payload(review)
    scout = IngestionScout()
    try:
        # force_commit: the human approval IS the HITL gate, so the
        # confidence threshold that quarantined this row must not re-fire.
        result = await scout.run_and_commit(payload, force_commit=True)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        logger.warning("commit failed for review %s: %s", review.pk, message)
        review.commit_error = message
        await sync_to_async(review.save)(update_fields=["commit_error"])
        provenance.log_event(
            "quarantine_commit_failed",
            {"review_id": review.pk, "source": review.source, "error": message},
        )
        return {"id": review.pk, "committed": False, "error": message, "edges": 0}

    review.committed_at = datetime.now(UTC)
    review.commit_error = ""
    await sync_to_async(review.save)(update_fields=["committed_at", "commit_error"])
    provenance.log_event(
        "quarantine_committed",
        {
            "review_id": review.pk,
            "source": review.source,
            "kind": review.kind,
            "reviewer": review.reviewer or "(unattributed)",
            "edges": result.get("edges", 0),
        },
    )
    return {
        "id": review.pk,
        "committed": bool(result.get("committed")),
        "edges": result.get("edges", 0),
    }


def commit_approved_reviews(limit: int = DEFAULT_SWEEP_LIMIT) -> list[dict[str, Any]]:
    """Commit every approved-but-uncommitted row (sync entry point).

    Used by the Celery task, the management command, and the admin action.
    """
    from law_ai.ingestionapp.models import PendingReview

    pending = list(
        PendingReview.objects.filter(approved=True, committed_at__isnull=True).order_by(
            "created_at"
        )[:limit]
    )
    if not pending:
        return []

    results: list[dict[str, Any]] = []
    for review in pending:
        try:
            results.append(async_to_sync(commit_approved_review)(review))
        except ApprovalError as exc:
            logger.warning("skipping review %s: %s", review.pk, exc)
            results.append({"id": review.pk, "committed": False, "error": str(exc)})
    committed = sum(1 for r in results if r.get("committed"))
    logger.info("approval sweep: %d/%d committed to the graph", committed, len(results))
    return results


__all__ = [
    "DEFAULT_SWEEP_LIMIT",
    "ApprovalError",
    "commit_approved_review",
    "commit_approved_reviews",
    "record_decision",
]
