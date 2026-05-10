"""Celery tasks for the ingestion app (spec 011 FR-11, AC-5)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("lawgraph.ingestionapp")


@shared_task(name="lawgraph.ingestionapp.quarantine_extraction", ignore_result=True)
def quarantine_extraction(payload: dict[str, Any]) -> str:
    """Persist a low-confidence extraction to ``PendingReview`` for HITL approval.

    The ``kind`` field discriminates between case opinions, statute sections,
    ordinance sections, derived documents, etc. (spec 015 FR-6); callers
    that omit it default to ``"case"`` for backwards compatibility with the
    spec-001 CourtListener path.
    """
    from lawgraph.audit.models import AuditEvent
    from lawgraph.ingestionapp.models import PendingReview
    from lawgraph.ingestionapp.quarantine_kinds import KIND_CASE, KNOWN_KINDS

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
