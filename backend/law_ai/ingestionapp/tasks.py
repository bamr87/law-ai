"""Celery tasks for the ingestion app (spec 011 FR-11, AC-5)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("law_ai.ingestionapp")


@shared_task(name="law_ai.ingestionapp.quarantine_extraction", ignore_result=True)
def quarantine_extraction(payload: dict[str, Any]) -> str:
    """Persist a low-confidence extraction to ``PendingReview`` for HITL approval.

    The ``kind`` field discriminates between case opinions, statute sections,
    ordinance sections, derived documents, etc. (spec 015 FR-6); callers
    that omit it default to ``"case"`` for backwards compatibility with the
    spec-001 CourtListener path.
    """
    from law_ai.audit.models import AuditEvent
    from law_ai.ingestionapp.models import PendingReview
    from law_ai.ingestionapp.quarantine_kinds import KIND_CASE, KNOWN_KINDS

    pid = str(payload.get("id") or payload.get("source") or "unknown")
    kind = str(payload.get("kind") or KIND_CASE)
    if kind not in KNOWN_KINDS:
        # Unknown kinds are accepted (CharField is forgiving) but logged so
        # operators can spot typos in upstream payloads.
        logger.warning("quarantine_extraction received unknown kind=%r", kind)

    PendingReview.objects.update_or_create(
        id=pid,
        defaults={
            "source": payload.get("source", "unknown"),
            "kind": kind,
            "payload": payload,
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "reason": payload.get("reason", "") or "",
        },
    )
    AuditEvent.objects.create(
        kind="ingestion_quarantine",
        payload={"id": pid, "source": payload.get("source"), "kind": kind},
    )
    return pid


@shared_task(name="law_ai.ingestionapp.commit_approved_reviews", ignore_result=True)
def commit_approved_reviews_task(limit: int | None = None) -> dict[str, int]:
    """Sweep approved-but-uncommitted quarantine rows into the graph.

    Spec 029 / BL-20260810-03: makes ``PendingReview.approved`` mean
    something. Idempotent — committed rows are skipped — so it is safe to
    run on a beat schedule as well as on demand.

    Constitution §12 I1 is preserved: the sweep delegates to
    ``IngestionScout.run_and_commit``; it never writes Neo4j itself.
    """
    from law_ai.ingestionapp.services.approval import (
        DEFAULT_SWEEP_LIMIT,
        commit_approved_reviews,
    )

    results = commit_approved_reviews(limit or DEFAULT_SWEEP_LIMIT)
    committed = sum(1 for r in results if r.get("committed"))
    failed = sum(1 for r in results if r.get("error"))
    return {"processed": len(results), "committed": committed, "failed": failed}
