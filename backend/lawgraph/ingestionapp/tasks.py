"""Celery tasks for the ingestion app (spec 011 FR-11, AC-5)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("lawgraph.ingestionapp")


@shared_task(name="lawgraph.ingestionapp.quarantine_extraction", ignore_result=True)
def quarantine_extraction(payload: dict[str, Any]) -> str:
    """Persist a low-confidence extraction to ``PendingReview`` for HITL approval."""
    from lawgraph.audit.models import AuditEvent
    from lawgraph.ingestionapp.models import PendingReview

    pid = str(payload.get("id") or payload.get("source") or "unknown")
    PendingReview.objects.update_or_create(
        id=pid,
        defaults={
            "source": payload.get("source", "unknown"),
            "payload": payload,
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "reason": payload.get("reason", "") or "",
        },
    )
    AuditEvent.objects.create(
        kind="ingestion_quarantine",
        payload={"id": pid, "source": payload.get("source")},
    )
    return pid
