"""Session-run ledger (WS4 — end-to-end change tracking).

Upsert helpers for :class:`lawgraph.audit.models.SessionRun`. An agent
work-session (a Claude Code run, a Copilot cycle, a Celery autonomy cycle)
calls :func:`start_session` when it begins and :func:`finalize_session` when it
ends; every provenance event tagged with the same ``session_id`` (see
``core.provenance``) then hangs off the row, giving one navigable
backlog → spec → commits → PR → audit-timeline entry.

Both helpers are **best-effort and never raise** — the ledger is an audit
surface, not part of the run's critical path (mirrors ``provenance._persist``).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger("lawgraph.audit.session_ledger")


def start_session(
    session_id: str,
    *,
    agent_source: str = "unknown",
    agent_name: str = "",
    kind: str = "",
    root_trace_id: str = "",
    spec_claimed: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Create the SessionRun row if absent; return it (or ``None`` on failure)."""
    if not session_id:
        return None
    try:
        from lawgraph.audit.models import SessionRun

        obj, _created = SessionRun.objects.get_or_create(
            session_id=session_id,
            defaults={
                "agent_source": agent_source,
                "agent_name": agent_name,
                "kind": kind,
                "root_trace_id": root_trace_id,
                "spec_claimed": spec_claimed,
                "status": "running",
                "metadata": metadata or {},
            },
        )
        return obj
    except Exception as exc:  # pragma: no cover - audit must not break the run
        logger.debug("session_ledger.start_session skipped: %s", exc)
        return None


def finalize_session(
    session_id: str,
    *,
    status: str = "completed",
    summary: str = "",
    backlog_items_added: list[str] | None = None,
    prs_created: list[Any] | None = None,
    spec_claimed: str = "",
    root_trace_id: str = "",
    ended_at: datetime.datetime | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> Any | None:
    """Mark the session finished (creating the row if it was never started)."""
    if not session_id:
        return None
    try:
        from lawgraph.audit.models import SessionRun

        obj = SessionRun.objects.filter(session_id=session_id).first()
        if obj is None:
            obj = SessionRun(session_id=session_id)
        obj.status = status
        obj.ended_at = ended_at or datetime.datetime.now(datetime.UTC)
        if summary:
            obj.summary = summary
        if backlog_items_added is not None:
            obj.backlog_items_added = list(backlog_items_added)
        if prs_created is not None:
            obj.prs_created = list(prs_created)
        if spec_claimed:
            obj.spec_claimed = spec_claimed
        if root_trace_id:
            obj.root_trace_id = root_trace_id
        if metadata_update:
            obj.metadata = {**(obj.metadata or {}), **metadata_update}
        obj.save()
        return obj
    except Exception as exc:  # pragma: no cover - audit must not break the run
        logger.debug("session_ledger.finalize_session skipped: %s", exc)
        return None
