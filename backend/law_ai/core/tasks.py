"""Celery tasks shared across apps (spec 011 FR-11)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import InterfaceError, OperationalError

logger = logging.getLogger("law_ai.tasks")

#: Transient database faults worth a retry rather than a failed cycle
#: (BL-20260511-23). A dropped connection or a Postgres restart mid-window
#: is exactly the case a nightly digest must survive; a programming error
#: is not, so nothing broader is listed here.
TRANSIENT_DB_ERRORS = (OperationalError, InterfaceError)


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
        _run_commit_approved,
        _run_corpus_growth,
        _run_digest,
        _run_lsat_content,
        _run_lsat_factory,
        _run_lsat_library,
        _run_test_pillar,
    )

    budget: int | None = kwargs.pop("budget", None)
    source: str | None = kwargs.pop("source", None)

    # PLR0911 is suppressed below: one `if` per autonomy kind is the clearest
    # form this dispatch can take; the pillar count, not the function, grew.
    def _runner(context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0911
        if kind == "test_pillar":
            return _run_test_pillar(context, budget=budget)
        if kind == "corpus_growth":
            return _run_corpus_growth(context, source=source, budget=budget)
        if kind == "digest":
            return _run_digest(context)
        if kind == "lsat_content":
            return _run_lsat_content(context, budget=budget)
        if kind == "lsat_factory":
            return _run_lsat_factory(context, budget=budget)
        if kind == "lsat_library":
            return _run_lsat_library(context, budget=budget)
        if kind == "commit_approved":
            return _run_commit_approved(context, budget=budget)
        raise ValueError(f"Unknown kind: {kind!r}")  # unreachable via beat config

    payload: dict[str, Any] = {
        "kind": kind,
        "budget": budget,
        "source": source,
        **kwargs,
    }
    return autonomy.run_cycle(kind, _runner, payload=payload)


@shared_task(  # type: ignore[untyped-decorator]
    bind=True,
    name="law_ai.core.tasks.compose_digest_task",
    ignore_result=False,
    autoretry_for=TRANSIENT_DB_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def compose_digest_task(self: Any, **kwargs: Any) -> dict[str, Any]:
    """Compose the daily autonomy digest, retrying transient DB faults.

    BL-20260511-23. Split out of the generic :func:`autonomy_cycle` for one
    reason: the digest is the only pillar whose whole job is a database
    query, so a dropped connection produces a *silently useless* artefact
    rather than a loud failure. ``compose_digest`` is therefore called with
    ``raise_on_db_error=True`` here, and the raised
    ``OperationalError``/``InterfaceError`` is retried up to three times with
    exponential backoff + jitter.

    Everything else is unchanged from the generic task:

    * the cycle still runs through :func:`law_ai.core.autonomy.run_cycle`, so
      the ``AUTONOMY_ENABLED`` kill-switch and the paired
      ``autonomy_cycle.start`` / ``autonomy_cycle.end`` provenance events
      still apply — including a ``status="error"`` end event on every failed
      attempt, so the audit trail shows the retries;
    * the digest path lands in the ``AuditEvent`` payload twice — once on the
      ``autonomy_digest.composed`` event and once via ``context`` on the
      ``autonomy_cycle.end`` event.
    """
    from law_ai.core import autonomy

    def _runner(context: dict[str, Any]) -> dict[str, Any]:
        digest_path = autonomy.compose_digest(raise_on_db_error=True)
        context["digest_path"] = str(digest_path)
        context["retries"] = int(getattr(self.request, "retries", 0) or 0)
        return {"digest_path": str(digest_path)}

    payload: dict[str, Any] = {"kind": "digest", **kwargs}
    return autonomy.run_cycle("digest", _runner, payload=payload)
