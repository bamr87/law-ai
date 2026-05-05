"""Celery tasks shared across apps (spec 011 FR-11)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("lexgraph.tasks")


@shared_task(name="lexgraph.core.persist_audit_event", ignore_result=True)
def persist_audit_event(event: dict[str, Any]) -> None:
    """Async fallback path for :func:`provenance._persist` when DB writes fail."""
    try:
        from lexgraph.audit.models import AuditEvent

        AuditEvent.objects.create(
            kind=event.get("type") or "unknown",
            trace_id=event.get("trace_id", "") or "",
            agent_version=event.get("agent_version", "") or "",
            payload=event,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("persist_audit_event failed: %s", exc)
