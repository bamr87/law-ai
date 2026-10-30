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
def autonomy_cycle(kind: str = "digest", **kwargs: Any) -> dict[str, Any]:
    """Celery task that wraps :func:`law_ai.core.autonomy.run_cycle`.

    This is the single entry-point task used by the beat schedule defined in
    ``law_ai.celery``. It forwards *kwargs* as the cycle ``payload`` so each
    beat entry can pass ``budget``, ``source``, etc. without needing separate
    task functions.

    The task is always safe to call: ``run_cycle`` short-circuits with
    ``status="disabled"`` when ``AUTONOMY_ENABLED=False`` (constitution §12 I3).
    """
    from law_ai.core import autonomy
    from law_ai.core.management.commands.run_autonomy import build_runner

    budget: int | None = kwargs.pop("budget", None)
    source: str | None = kwargs.pop("source", None)

    # One dispatch table for both entry points (BL-20260906-26). This used to
    # be a second copy of the command's if-chain, and it silently fell behind
    # it: the `lsat_cross_check` beat entry raised `Unknown kind` here while
    # `manage.py run_autonomy --kind lsat_cross_check` worked.
    runner = build_runner(kind, source=source, budget=budget)

    payload: dict[str, Any] = {
        "kind": kind,
        "budget": budget,
        "source": source,
        **kwargs,
    }
    return autonomy.run_cycle(kind, runner, payload=payload)


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

    BL-20260511-05: composing is only half the job. This is the task the
    07:00 UTC ``autonomy-daily-digest`` beat entry runs, so it is also where
    delivery has to happen — wiring ``deliver_digest`` only into the manual
    ``run_autonomy --kind digest`` command left the *scheduled* digest with
    the file as its only surface, which is exactly the failure the item
    names. Delivery is deliberately outside the retry contract above:
    :func:`~law_ai.core.autonomy.deliver_digest` never raises and no-ops when
    no channel is configured, so a dead webhook can neither fail the cycle nor
    trigger a re-compose of a digest that was already written correctly.
    """
    from law_ai.core import autonomy

    def _runner(context: dict[str, Any]) -> dict[str, Any]:
        digest_path = autonomy.compose_digest(raise_on_db_error=True)
        context["digest_path"] = str(digest_path)
        context["retries"] = int(getattr(self.request, "retries", 0) or 0)
        delivery = autonomy.deliver_digest(digest_path)
        context["digest_delivered"] = delivery["delivered"]
        return {"digest_path": str(digest_path), "delivery": delivery}

    payload: dict[str, Any] = {"kind": "digest", **kwargs}
    return autonomy.run_cycle("digest", _runner, payload=payload)
