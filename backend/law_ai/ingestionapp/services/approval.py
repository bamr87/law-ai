"""Approval → commit path for quarantined documents (spec 029, BL-20260810-03).

Before this module, ``PendingReview.approved`` had **no consumer**: a human
could flip it in Django admin and nothing happened — approved knowledge
never reached Neo4j, so the corpus could not grow through the sanctioned
HITL path. This closes that loop.

Invariants
----------
- **§12 I1** — graph writes go through the owning scout with
  ``force_commit=True`` (the human approval *is* the gate): case rows via
  ``IngestionScout.run_and_commit``, statute sections via
  ``StatuteScout.commit_section`` (BL-20260811-03). This module never
  touches Neo4j directly.
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
    reviewer_user: Any | None = None,
    note: str = "",
) -> None:
    """Persist a human review decision with its author and rationale (§4).

    ``reviewer_user`` (BL-20260811-04) binds the decision to a real Django
    account when one made it; ``reviewer`` remains the legacy free-text
    attribution every non-account surface (CLI, env-key API) still uses. When
    a user is given its username wins over any claimed string, so the row and
    the audit event agree with the FK.

    Does **not** commit — approval and commit are separate steps so a graph
    outage cannot silently discard a reviewer's decision.
    """
    from law_ai.core.reviewer import reviewer_from_user

    identity = reviewer_from_user(reviewer_user)
    attribution = identity.name if identity.is_account else (reviewer or "")
    review.approved = approved
    review.reviewed_at = datetime.now(UTC)
    review.reviewer = attribution
    review.review_note = note or ""
    fields = ["approved", "reviewed_at", "reviewer", "review_note"]
    if identity.is_account:
        review.reviewer_user = identity.user
        fields.append("reviewer_user")
    review.save(update_fields=fields)
    provenance.log_event(
        "quarantine_decision",
        {
            "review_id": review.pk,
            "source": review.source,
            "kind": review.kind,
            "approved": approved,
            "reviewer": attribution or "(unattributed)",
            "reviewer_user_id": identity.user_id,
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


async def _commit_by_kind(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Route an approved payload to the extractor its ``kind`` requires.

    BL-20260811-03: every kind used to go through ``IngestionScout``, a
    ``:Case`` extractor, so an approved ``statute_section`` row could not
    reach the graph at all. Unsupported kinds fail loudly here and the
    failure is recorded on the row — better than a silent skip that looks
    like a successful approval.

    Constitution §12 I1 is preserved either way: this module never writes
    Neo4j itself, it delegates to the owning scout.
    """
    from law_ai.ingestionapp.quarantine_kinds import (
        KIND_CASE,
        KIND_ORDINANCE_SECTION,
        KIND_STATUTE_SECTION,
    )

    resolved = kind or KIND_CASE
    if resolved == KIND_CASE:
        from law_ai.ingestionapp.services.scout import IngestionScout

        return await IngestionScout().run_and_commit(payload, force_commit=True)
    if resolved == KIND_STATUTE_SECTION:
        from law_ai.ingestionapp.services.statute_scout import StatuteScout

        return await StatuteScout().commit_section(payload, force_commit=True)
    if resolved == KIND_ORDINANCE_SECTION:
        # BL-20260509-05. Municipal ordinances are quarantined unconditionally
        # (their source adapter requires human approval), so this branch is not
        # an edge case for them — it is the *only* way an ordinance reaches the
        # graph.
        from law_ai.ingestionapp.services.ordinance_scout import OrdinanceScout

        return await OrdinanceScout().commit_section(payload, force_commit=True)
    raise ApprovalError(
        f"unsupported quarantine kind {resolved!r}: no commit path is "
        "implemented for it yet"
    )


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

    payload = _extraction_payload(review)
    try:
        # force_commit: the human approval IS the HITL gate, so the
        # confidence threshold that quarantined this row must not re-fire.
        result = await _commit_by_kind(review.kind, payload)
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
            "reviewer_user_id": getattr(review, "reviewer_user_id", None),
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


def _reextract_by_kind(kind: str, payload: dict[str, Any]) -> tuple[float, bool, int]:
    """Re-score a quarantined payload with today's extractor for its ``kind``.

    Returns ``(confidence, clears_threshold, n_citations)``. Case rows are
    re-parsed from the stored raw document; statute rows are re-scored from
    the stored section, because the quarantine envelope carries the parsed
    section rather than the title HTML (BL-20260905-96). Kinds with no
    re-extraction path fail loudly, the way the commit path does.
    """
    from law_ai.ingestionapp.quarantine_kinds import KIND_CASE, KIND_STATUTE_SECTION

    if kind == KIND_CASE:
        from law_ai.ingestionapp.services.scout import IngestionScout

        result = IngestionScout().extract(payload)
        return result.confidence, result.is_high_confidence(), len(result.citations)
    if kind == KIND_STATUTE_SECTION:
        from law_ai.ingestionapp.services.statute_scout import (
            CONFIDENCE_THRESHOLD,
            StatuteScout,
        )

        section = StatuteScout().rescore(payload)
        return section.confidence, section.confidence >= CONFIDENCE_THRESHOLD, 0
    raise ApprovalError(
        f"kind={kind!r} has no re-extraction path; re-extraction supports "
        "case and statute_section rows"
    )


def reextract_review(review: Any, *, reviewer: str = "") -> dict[str, Any]:
    """Re-run the extractor over a quarantined row's stored raw document.

    Third review verb alongside approve/reject (BL-20260503-10, spec 011
    T-354). A row is quarantined because *the extractor of the day* scored
    it below the threshold; once the extractor improves, a reviewer wants to
    ask "would it still be quarantined today?" without re-fetching the
    source. ``PendingReview.payload`` already carries the raw document
    (``IngestionScout._quarantine_via_celery`` stores it under
    ``payload["payload"]``), so re-extraction is purely local. Statute rows
    carry the parsed section rather than the title HTML, so they are
    re-scored instead of re-parsed (BL-20260905-96); see
    :func:`_reextract_by_kind`.

    Refreshes ``confidence`` and ``reason`` on the row and emits a
    provenance event. It deliberately does **not** commit, even when the
    fresh score clears the threshold: constitution §5 makes the human
    approval the gate, so a re-extraction can only ever *inform* a reviewer,
    never bypass them.
    """
    from law_ai.ingestionapp.quarantine_kinds import KIND_CASE

    kind = review.kind or KIND_CASE
    if review.committed_at is not None:
        return {
            "id": review.pk,
            "reextracted": False,
            "skipped": "already-committed",
        }

    payload = _extraction_payload(review)
    previous = review.confidence
    try:
        confidence, clears, n_citations = _reextract_by_kind(kind, payload)
    except ApprovalError:
        raise
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        logger.warning("re-extraction failed for review %s: %s", review.pk, message)
        review.commit_error = message
        review.save(update_fields=["commit_error"])
        provenance.log_event(
            "quarantine_reextract_failed",
            {"review_id": review.pk, "source": review.source, "error": message},
        )
        return {"id": review.pk, "reextracted": False, "error": message}

    review.confidence = confidence
    review.reason = (
        "re-extracted: now clears the confidence threshold, awaiting approval"
        if clears
        else f"low_confidence (re-extracted at {confidence:.3f})"
    )
    review.commit_error = ""
    review.save(update_fields=["confidence", "reason", "commit_error"])
    provenance.log_event(
        "quarantine_reextracted",
        {
            "review_id": review.pk,
            "source": review.source,
            "kind": kind,
            "reviewer": reviewer or "(unattributed)",
            "previous_confidence": previous,
            "confidence": confidence,
            "clears_threshold": clears,
            "n_citations": n_citations,
        },
    )
    return {
        "id": review.pk,
        "reextracted": True,
        "previous_confidence": previous,
        "confidence": confidence,
        "clears_threshold": clears,
        "n_citations": n_citations,
    }


__all__ = [
    "DEFAULT_SWEEP_LIMIT",
    "ApprovalError",
    "commit_approved_review",
    "commit_approved_reviews",
    "record_decision",
    "reextract_review",
]
