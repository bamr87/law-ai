"""Celery tasks shared across apps (spec 011 FR-11)."""

from __future__ import annotations

import logging
from pathlib import Path
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


@shared_task(  # type: ignore[untyped-decorator]
    name="law_ai.core.tasks.governance_triage", ignore_result=False
)
def governance_triage(stale_days: int = 60) -> dict[str, Any]:
    """Periodic spec + backlog triage (BL-20260503-14).

    Runs ``scripts/spec_validator.py`` and ``scripts/backlog_lint.py`` over the
    checked-out repo and, when a GitHub credential is configured, keeps one
    idempotent triage issue up to date. See :mod:`law_ai.core.governance`.

    Not routed through ``autonomy_cycle`` and not on the ``autonomy`` queue:
    reading two validators and reporting what they said is not an autonomous
    *decision*, and it has to keep working on an instance with
    ``AUTONOMY_ENABLED=false``.
    """
    from django.conf import settings

    from law_ai.core.governance import run_triage
    from law_ai.core.provenance import provenance

    result = run_triage(
        Path(settings.REPO_ROOT),
        stale_days=stale_days,
        repo=getattr(settings, "GOVERNANCE_TRIAGE_GITHUB_REPO", ""),
        token=getattr(settings, "GOVERNANCE_TRIAGE_GITHUB_TOKEN", ""),
    )
    provenance.log_event(
        "governance_triage",
        {
            "source": "beat",
            "repo_available": result["repo_available"],
            "backlog_stale": result["backlog_stale"],
            "spec_ok": result["spec_ok"],
            "issue": result["issue"],
        },
    )
    if result["needs_triage"]:
        logger.warning(
            "governance triage: backlog_stale=%s spec_ok=%s issue=%s",
            result["backlog_stale"],
            result["spec_ok"],
            result["issue"],
        )
    return result
