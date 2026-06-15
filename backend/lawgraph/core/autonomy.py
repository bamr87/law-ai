"""Audited entry point for every autonomy loop (spec 018, constitution §12).

All recursive / scheduled agent loops in this repo MUST be invoked through
:func:`run_cycle`. The wrapper:

* short-circuits when ``AUTONOMY_ENABLED`` is ``False`` and emits a single
  ``autonomy_disabled`` provenance event (invariant **I3**, kill-switch);
* emits paired ``autonomy_cycle.start`` + ``autonomy_cycle.end`` events with
  a shared ``cycle_id`` so a single trace can be reconstructed from the
  audit log (invariant **I4**, one audited entry point);
* converts uncaught runner exceptions into ``autonomy_cycle.end`` events
  with ``status='error'`` so failures cannot escape the audit log;
* exposes :func:`record_policy_violation` so callers (e.g. dispatchers
  that detect a non-allow-listed source) can record a structured event
  before refusing to act.

This module deliberately has **no** Neo4j writes, **no** LLM calls, and
**no** Celery side-effects. It is a thin, side-effect-free wrapper around
:mod:`lawgraph.core.provenance` so it can be unit-tested without spinning
up Postgres / Redis / Ollama.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings

from lawgraph.core.provenance import _persist

logger = logging.getLogger("lawgraph.autonomy")


# ---------------------------------------------------------------------------
# Settings accessors (kept tiny so tests can monkeypatch ``settings`` only).
# ---------------------------------------------------------------------------
def is_enabled() -> bool:
    """Return ``True`` only when ``settings.AUTONOMY_ENABLED`` is truthy."""
    return bool(getattr(settings, "AUTONOMY_ENABLED", False))


def allowed_sources() -> tuple[str, ...]:
    """Return the configured allow-list as an immutable tuple."""
    raw: Iterable[str] = getattr(settings, "AUTONOMY_ALLOWED_SOURCES", ()) or ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


def is_source_allowed(source_name: str) -> bool:
    """Return ``True`` iff ``source_name`` appears in the allow-list."""
    return source_name in allowed_sources()


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------
def _event(event_type: str, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    payload.update(fields)
    return payload


def record_policy_violation(
    *,
    cycle_id: str,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record a structured ``policy_violation`` event.

    Callers MUST invoke this before refusing an action that breaks an
    invariant (e.g. dispatching a non-allow-listed source). The event is
    written via :func:`lawgraph.core.provenance._persist` so it lands in
    both the JSONL audit store and the ``audit.AuditEvent`` table.
    """
    event = _event(
        "policy_violation",
        cycle_id=cycle_id,
        reason=reason,
        details=payload or {},
    )
    logger.warning("autonomy policy violation: %s", reason)
    _persist(event)


def record_disabled(
    *,
    cycle_type: str,
    payload: dict[str, Any] | None = None,
    cycle_id: str | None = None,
) -> str:
    """Record a single ``autonomy_disabled`` event and return its cycle_id."""
    cycle_id = cycle_id or str(uuid4())
    event = _event(
        "autonomy_disabled",
        cycle_id=cycle_id,
        cycle_type=cycle_type,
        details=payload or {},
    )
    logger.info("autonomy short-circuited (kill-switch): %s", cycle_type)
    _persist(event)
    return cycle_id


# ---------------------------------------------------------------------------
# Change-ledger (WS4): mirror each cycle into a SessionRun row. Best-effort —
# the ledger never breaks a cycle.
# ---------------------------------------------------------------------------
_STATUS_TO_LEDGER = {"ok": "completed", "error": "failed", "disabled": "disabled"}


def _ledger_start(
    cycle_id: str, cycle_type: str, payload: dict[str, Any] | None
) -> None:
    from lawgraph.audit import session_ledger

    session_ledger.start_session(
        cycle_id,
        agent_source="celery",
        agent_name="AutonomyOrchestrator",
        kind=cycle_type,
        root_trace_id=cycle_id,
        metadata={"payload_keys": sorted((payload or {}).keys())},
    )


def _ledger_finalize(cycle_id: str, context: dict[str, Any]) -> None:
    from lawgraph.audit import session_ledger

    extra = {
        k: v
        for k, v in context.items()
        if k not in {"cycle_id", "cycle_type", "status", "result"}
    }
    result = context.get("result")
    session_ledger.finalize_session(
        cycle_id,
        status=_STATUS_TO_LEDGER.get(str(context.get("status")), "completed"),
        summary=str(result)[:1000] if result is not None else "",
        metadata_update=extra or None,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
@contextmanager
def _cycle_span(
    cycle_type: str,
    payload: dict[str, Any] | None,
    *,
    cycle_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Internal context manager emitting paired start/end events.

    Yields a mutable ``context`` dict the caller may extend with fields
    that should appear on the ``autonomy_cycle.end`` event (e.g. counts,
    PR url, digest path).
    """
    cycle_id = cycle_id or str(uuid4())
    context: dict[str, Any] = {
        "cycle_id": cycle_id,
        "cycle_type": cycle_type,
        "status": "ok",
    }
    start_event = _event(
        "autonomy_cycle.start",
        cycle_id=cycle_id,
        cycle_type=cycle_type,
        payload=payload or {},
    )
    _persist(start_event)
    _ledger_start(cycle_id, cycle_type, payload)
    started = time.monotonic()
    try:
        yield context
    except Exception as exc:  # pragma: no cover - exercised in tests
        context["status"] = "error"
        context["error"] = repr(exc)
        raise
    finally:
        end_event = _event(
            "autonomy_cycle.end",
            cycle_id=cycle_id,
            cycle_type=cycle_type,
            duration_ms=round((time.monotonic() - started) * 1000.0, 2),
            **{k: v for k, v in context.items() if k not in {"cycle_id", "cycle_type"}},
        )
        _persist(end_event)
        _ledger_finalize(cycle_id, context)


def run_cycle(
    cycle_type: str,
    runner: Callable[[dict[str, Any]], Any],
    *,
    payload: dict[str, Any] | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Invoke ``runner`` inside a fully-audited autonomy cycle.

    Parameters
    ----------
    cycle_type:
        Free-form label for the loop (e.g. ``"test_pillar"``,
        ``"corpus_growth"``, ``"digest"``). Recorded on every event so
        operators can filter the audit log.
    runner:
        Callable invoked with the mutable ``context`` dict; the return
        value is also stored on ``context['result']`` so it appears on
        the ``autonomy_cycle.end`` event.
    payload:
        Optional structured input recorded on the ``start`` event.

    Returns
    -------
    dict
        The final ``context`` dict (with ``status`` set to ``"ok"``,
        ``"disabled"``, or ``"error"``).

    Notes
    -----
    Honors the ``AUTONOMY_ENABLED`` kill-switch: when disabled the
    runner is **not** invoked and a single ``autonomy_disabled`` event
    is recorded instead.
    """
    # Honour caller-supplied idempotency key (--cycle-id CLI flag).
    _cycle_id: str | None = cycle_id or (payload or {}).get("cycle_id")  # type: ignore[assignment]

    if not is_enabled():
        _cid = record_disabled(
            cycle_type=cycle_type, payload=payload, cycle_id=_cycle_id
        )
        return {
            "cycle_id": _cid,
            "cycle_type": cycle_type,
            "status": "disabled",
        }

    with _cycle_span(cycle_type, payload, cycle_id=_cycle_id) as context:
        result = runner(context)
        context["result"] = result
    return context


__all__ = [
    "allowed_sources",
    "compose_digest",
    "is_enabled",
    "is_source_allowed",
    "record_disabled",
    "record_policy_violation",
    "run_cycle",
]


# ---------------------------------------------------------------------------
# Default output directory  (operators can override via AUTONOMY_DIGEST_DIR)
# ---------------------------------------------------------------------------
_DEFAULT_DIGEST_DIR = Path(__file__).parent.parent.parent / "var" / "autonomy"


def compose_digest(*, date: datetime | None = None) -> Path:
    """Aggregate the last 24 h of ``autonomy_*`` audit events into a Markdown file.

    Parameters
    ----------
    date:
        Anchor date for the digest window (end = midnight of this date's
        UTC day; defaults to *now*). Pass an explicit value in tests to
        keep output deterministic.

    Returns
    -------
    pathlib.Path
        Absolute path to the written digest file
        ``<AUTONOMY_DIGEST_DIR>/digest-YYYY-MM-DD.md``.

    Notes
    -----
    * Never raises — on DB failure an empty digest with an error note is
      written so the caller always gets a usable path.
    * Every call appends an ``autonomy_digest.composed`` provenance event.
    """
    now: datetime = date or datetime.now(UTC)
    window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(hours=24)
    date_label = window_end.strftime("%Y-%m-%d")

    digest_dir = Path(
        str(getattr(settings, "AUTONOMY_DIGEST_DIR", _DEFAULT_DIGEST_DIR))
    )
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / f"digest-{date_label}.md"

    # ------------------------------------------------------------------
    # Query AuditEvent rows for the window
    # ------------------------------------------------------------------
    prs_opened: list[str] = []
    backlog_appended: list[str] = []
    docs_quarantined: list[str] = []
    legalbench_deltas: list[str] = []
    error_note: str = ""

    try:
        from lawgraph.audit.models import AuditEvent

        rows = AuditEvent.objects.filter(
            kind__startswith="autonomy_",
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).order_by("timestamp")

        for row in rows:
            payload: dict[str, Any] = row.payload or {}
            kind = row.kind
            if kind == "autonomy_pr_opened":
                prs_opened.append(payload.get("url") or payload.get("pr_url") or "?")
            elif kind == "autonomy_backlog_appended":
                backlog_appended.append(payload.get("bl_id") or "?")
            elif kind == "autonomy_doc_quarantined":
                docs_quarantined.append(
                    payload.get("source_url") or payload.get("doc_id") or "?"
                )
            elif kind == "autonomy_legalbench_delta":
                task_name = payload.get("task") or "?"
                delta = payload.get("delta", "?")
                legalbench_deltas.append(
                    f"{task_name}: {delta:+}"
                    if isinstance(delta, (int, float))
                    else f"{task_name}: {delta}"
                )
    except Exception as exc:
        logger.warning("compose_digest DB query failed: %s", exc)
        error_note = f"\n> **Error querying audit log**: {exc}\n"

    # ------------------------------------------------------------------
    # Render Markdown
    # ------------------------------------------------------------------
    lines: list[str] = [
        f"# Autonomy Digest — {date_label}",
        f"> Window: {window_start.isoformat()} → {window_end.isoformat()} UTC",
        "",
    ]
    if error_note:
        lines.append(error_note)

    lines += [
        "## PRs Opened",
        *([f"- {u}" for u in prs_opened] or ["- *(none)*"]),
        "",
        "## BACKLOG Items Appended",
        *([f"- {b}" for b in backlog_appended] or ["- *(none)*"]),
        "",
        "## Docs Quarantined",
        *([f"- {d}" for d in docs_quarantined] or ["- *(none)*"]),
        "",
        "## LegalBench Delta",
        *([f"- {item}" for item in legalbench_deltas] or ["- *(none)*"]),
        "",
    ]

    digest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("autonomy digest written: %s", digest_path)

    _persist(
        _event(
            "autonomy_digest.composed",
            digest_path=str(digest_path),
            date_label=date_label,
            prs=len(prs_opened),
            backlog=len(backlog_appended),
            docs=len(docs_quarantined),
            legalbench=len(legalbench_deltas),
        )
    )
    return digest_path
