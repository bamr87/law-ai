"""Celery tasks shared across apps (spec 011 FR-11)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("law_ai.tasks")


@shared_task(name="law_ai.core.persist_audit_event", ignore_result=True)
def persist_audit_event(event: dict[str, Any]) -> None:
    """Async fallback path for :func:`provenance._persist` when DB writes fail."""
    try:
        from law_ai.audit.models import AuditEvent

        AuditEvent.objects.create(
            kind=event.get("type") or "unknown",
            trace_id=event.get("trace_id", "") or "",
            agent_version=event.get("agent_version", "") or "",
            payload=event,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("persist_audit_event failed: %s", exc)


@shared_task(name="law_ai.core.tasks.autonomy_cycle", ignore_result=False)
def autonomy_cycle(kind: str = "test_pillar", **kwargs: Any) -> dict[str, Any]:
    """Celery task that wraps :func:`law_ai.core.autonomy.run_cycle`.

    This is the single entry-point task used by the beat schedule defined in
    ``law_ai.celery``. It forwards *kwargs* as the cycle ``payload`` so each
    beat entry can pass ``budget``, ``source``, etc. without needing separate
    task functions.

    The task is always safe to call: ``run_cycle`` short-circuits with
    ``status="disabled"`` when ``AUTONOMY_ENABLED=False`` (constitution §12 I3).
    """
    from law_ai.core import autonomy
    from law_ai.core.management.commands.run_autonomy import (
        _run_corpus_growth,
        _run_digest,
        _run_lsat_content,
        _run_test_pillar,
    )

    budget: int | None = kwargs.pop("budget", None)
    source: str | None = kwargs.pop("source", None)

    def _runner(context: dict[str, Any]) -> dict[str, Any]:
        if kind == "test_pillar":
            return _run_test_pillar(context, budget=budget)
        if kind == "corpus_growth":
            return _run_corpus_growth(context, source=source, budget=budget)
        if kind == "digest":
            return _run_digest(context)
        if kind == "lsat_content":
            return _run_lsat_content(context, budget=budget)
        raise ValueError(f"Unknown kind: {kind!r}")  # unreachable via beat config

    payload: dict[str, Any] = {
        "kind": kind,
        "budget": budget,
        "source": source,
        **kwargs,
    }
    return autonomy.run_cycle(kind, _runner, payload=payload)
