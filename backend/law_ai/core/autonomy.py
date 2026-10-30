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
:mod:`law_ai.core.provenance` so it can be unit-tested without spinning
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

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.provenance import _in_async_context, _persist

logger = logging.getLogger("law_ai.autonomy")

#: How far back the JSONL fallback scans for a prior cycle with the same
#: ``cycle_id`` (BL-20260511-29). Matches ``KEEP_AUDIT_LINES``' order of
#: magnitude so a replay check is bounded even on a busy audit file.
_REPLAY_SCAN_LINES = 5000


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
    written via :func:`law_ai.core.provenance._persist` so it lands in
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
# Idempotency (BL-20260511-29): --cycle-id replays instead of re-running
# ---------------------------------------------------------------------------
def _find_prior_cycle(cycle_id: str) -> dict[str, Any] | None:
    """Return the ``autonomy_cycle.end`` event for *cycle_id*, or ``None``.

    Two lookups, in order:

    1. The ``audit.AuditEvent`` table, which is queryable and survives audit
       log rotation. Skipped in an async context, where Django's ORM raises
       ``SynchronousOnlyOperation`` (same rule ``provenance._persist`` uses),
       and tolerant of any DB failure — an unreachable Postgres must not turn
       an idempotency *check* into a cycle failure.
    2. The JSONL audit store. This is not merely a test convenience: on the
       daphne/ASGI path and in a container with no DB the JSONL file is the
       only record, so without this leg a reused ``cycle_id`` would silently
       re-run the cycle.
    """
    if not cycle_id:
        return None

    if not _in_async_context():
        try:
            from law_ai.audit.models import AuditEvent

            row = (
                AuditEvent.objects.filter(
                    kind="autonomy_cycle.end", payload__cycle_id=cycle_id
                )
                .order_by("-timestamp")
                .first()
            )
            if row is not None and isinstance(row.payload, dict):
                return dict(row.payload)
        except Exception as exc:
            logger.debug("cycle_id lookup via ORM unavailable: %s", exc)

    for event in audit_store.tail(_REPLAY_SCAN_LINES):
        if event.get("type") == "autonomy_cycle.end" and (
            event.get("cycle_id") == cycle_id
        ):
            return event
    return None


def _replay(prior: dict[str, Any], cycle_type: str, cycle_id: str) -> dict[str, Any]:
    """Emit an ``autonomy_cycle.replayed`` event and return the prior result."""
    replayed: dict[str, Any] = {
        "cycle_id": cycle_id,
        "cycle_type": prior.get("cycle_type") or cycle_type,
        "status": prior.get("status", "ok"),
        "result": prior.get("result"),
        "replayed": True,
    }
    if prior.get("error"):
        replayed["error"] = prior["error"]
    logger.info(
        "autonomy cycle %s already ran (status=%s); replaying prior result",
        cycle_id,
        replayed["status"],
    )
    _persist(
        _event(
            "autonomy_cycle.replayed",
            cycle_id=cycle_id,
            cycle_type=replayed["cycle_type"],
            prior_status=replayed["status"],
        )
    )
    return replayed


# ---------------------------------------------------------------------------
# AutonomyRun projection (BL-20260511-04)
#
# The `autonomy_cycle.*` AuditEvent rows stay exactly as they were — the audit
# layer is never bypassed (constitution §4). These helpers additionally
# project each cycle into the queryable `audit.AutonomyRun` table so the
# digest and the dashboard can order, filter and count runs instead of
# scanning JSON payloads. Both are best-effort: a DB outage degrades a report,
# it never fails a cycle.
# ---------------------------------------------------------------------------
def _open_run_row(
    cycle_id: str, cycle_type: str, payload: dict[str, Any] | None
) -> Any:
    """Insert the ``AutonomyRun`` row for a starting cycle, or ``None``."""
    if _in_async_context():
        return None
    try:
        from law_ai.audit.models import AutonomyRun

        data = payload or {}
        return AutonomyRun.objects.create(
            cycle_id=cycle_id,
            kind=cycle_type,
            source=str(data.get("source") or ""),
            started_at=datetime.now(UTC),
            status="ok",
        )
    except Exception as exc:
        logger.debug("AutonomyRun row not opened (%s); events still recorded", exc)
        return None


def _close_run_row(row: Any, context: dict[str, Any], duration_ms: float) -> None:
    """Finish the ``AutonomyRun`` row with the cycle's outcome."""
    if row is None:
        return
    try:
        row.ended_at = datetime.now(UTC)
        row.duration_ms = duration_ms
        row.status = str(context.get("status", "ok"))
        row.error = str(context.get("error", "") or "")
        row.trace_id = str(context.get("trace_id", "") or "")
        row.summary = {
            k: v
            for k, v in context.items()
            if k not in {"cycle_id", "cycle_type", "status", "error", "trace_id"}
        }
        row.save(
            update_fields=[
                "ended_at",
                "duration_ms",
                "status",
                "error",
                "trace_id",
                "summary",
            ]
        )
    except Exception as exc:
        logger.debug("AutonomyRun row not closed (%s); events still recorded", exc)


def _record_terminal_run(
    cycle_id: str, cycle_type: str, status: str, payload: dict[str, Any] | None
) -> None:
    """Record a cycle that never ran a runner (disabled, or replayed)."""
    if _in_async_context():
        return
    try:
        from law_ai.audit.models import AutonomyRun

        now = datetime.now(UTC)
        AutonomyRun.objects.create(
            cycle_id=cycle_id,
            kind=cycle_type,
            source=str((payload or {}).get("source") or ""),
            started_at=now,
            ended_at=now,
            status=status,
            duration_ms=0.0,
            summary={},
        )
    except Exception as exc:
        logger.debug("AutonomyRun row not recorded (%s); events still written", exc)


# ---------------------------------------------------------------------------
# Progress streaming (BL-20260811-15)
#
# A cycle can run for minutes with nothing to show for it until the digest
# lands. When the caller supplies a `stream_id` — `--stream-id` on the CLI, a
# `stream_id` kwarg on the Celery task — each cycle boundary is also published
# to the `agent-run-<stream_id>` WebSocket group the analysis studio already
# uses, so an operator can watch a cycle instead of tailing a log. Absent a
# stream id this is a no-op, and a channel-layer failure never touches the
# cycle: `emit_stream_event_sync` swallows its own errors.
# ---------------------------------------------------------------------------
def _emit_cycle_event(stream_id: str | None, payload: dict[str, Any]) -> None:
    """Publish one cycle progress event, when a client asked for a stream."""
    if not stream_id:
        return
    from law_ai.agentsapi.streaming import emit_stream_event_sync

    emit_stream_event_sync(stream_id, payload, source="autonomy")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
@contextmanager
def _cycle_span(
    cycle_type: str,
    payload: dict[str, Any] | None,
    *,
    cycle_id: str | None = None,
    stream_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Internal context manager emitting paired start/end events.

    Yields a mutable ``context`` dict the caller may extend with fields
    that should appear on the ``autonomy_cycle.end`` event (e.g. counts,
    PR url, digest path).

    When ``stream_id`` is set the same two boundaries are also pushed to that
    WebSocket group, and the id is recorded on the cycle's own audit events so
    a trace can be tied back to the socket that watched it (BL-20260811-15).
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
    # BL-20260511-04: the queryable projection of this same cycle. Best-effort
    # by construction — `_open_run_row` returns None rather than raising.
    run_row = _open_run_row(cycle_id, cycle_type, payload)
    if stream_id:
        context["stream_id"] = stream_id
    _emit_cycle_event(
        stream_id,
        {
            "type": "autonomy_step",
            "stage": "start",
            "cycle_id": cycle_id,
            "cycle_type": cycle_type,
        },
    )
    started = time.monotonic()
    try:
        yield context
    except Exception as exc:  # pragma: no cover - exercised in tests
        context["status"] = "error"
        context["error"] = repr(exc)
        raise
    finally:
        duration_ms = round((time.monotonic() - started) * 1000.0, 2)
        end_event = _event(
            "autonomy_cycle.end",
            cycle_id=cycle_id,
            cycle_type=cycle_type,
            duration_ms=duration_ms,
            **{k: v for k, v in context.items() if k not in {"cycle_id", "cycle_type"}},
        )
        _persist(end_event)
        _close_run_row(run_row, context, duration_ms)
        _emit_cycle_event(
            stream_id,
            {
                "type": "complete",
                "cycle_id": cycle_id,
                "cycle_type": cycle_type,
                "status": context.get("status", "ok"),
                "duration_ms": duration_ms,
                # The digest path is the one artefact an operator wants a link
                # to the moment a cycle ends; everything else is in the audit
                # event this same block just persisted.
                "digest_path": context.get("digest_path"),
                "error": context.get("error"),
            },
        )


def run_cycle(
    cycle_type: str,
    runner: Callable[[dict[str, Any]], Any],
    *,
    payload: dict[str, Any] | None = None,
    cycle_id: str | None = None,
    stream_id: str | None = None,
) -> dict[str, Any]:
    """Invoke ``runner`` inside a fully-audited autonomy cycle.

    Parameters
    ----------
    cycle_type:
        Free-form label for the loop (e.g. ``"lsat_content"``,
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

    cycle_id:
        Optional idempotency key (also read from ``payload['cycle_id']``,
        which is how the ``--cycle-id`` CLI flag arrives). When a cycle
        with this id has already ended, the runner is **not** invoked:
        the prior result is returned with ``replayed=True`` and a single
        ``autonomy_cycle.replayed`` event is recorded (BL-20260511-29).

    stream_id:
        Optional WebSocket correlation id (also read from
        ``payload['stream_id']``, which is how ``--stream-id`` and the
        Celery task kwarg arrive). When set, cycle start/end are pushed to
        ``agent-run-<stream_id>`` so a long cycle is watchable
        (BL-20260811-15). Purely additive: nothing about the cycle changes.

    Notes
    -----
    Honors the ``AUTONOMY_ENABLED`` kill-switch: when disabled the
    runner is **not** invoked and a single ``autonomy_disabled`` event
    is recorded instead. The kill-switch is checked *before* the replay
    lookup, so a disabled deployment stays disabled even for a cycle_id
    that ran before it was switched off.
    """
    # Honour caller-supplied idempotency key (--cycle-id CLI flag).
    _cycle_id: str | None = cycle_id or (payload or {}).get("cycle_id")
    _stream_id: str | None = stream_id or (payload or {}).get("stream_id")

    if not is_enabled():
        _cid = record_disabled(
            cycle_type=cycle_type, payload=payload, cycle_id=_cycle_id
        )
        _record_terminal_run(_cid, cycle_type, "disabled", payload)
        return {
            "cycle_id": _cid,
            "cycle_type": cycle_type,
            "status": "disabled",
        }

    if _cycle_id:
        prior = _find_prior_cycle(_cycle_id)
        if prior is not None:
            _record_terminal_run(_cycle_id, cycle_type, "replayed", payload)
            return _replay(prior, cycle_type, _cycle_id)

    with _cycle_span(
        cycle_type, payload, cycle_id=_cycle_id, stream_id=_stream_id
    ) as context:
        result = runner(context)
        context["result"] = result
    return context


__all__ = [
    "allowed_sources",
    "compose_digest",
    "deliver_digest",
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


def _digest_cycles(
    window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    """Return the ``AutonomyRun`` rows in the digest window (BL-20260511-04).

    The promoted table answers "what ran, how did it end, how long did it
    take" with an indexed range scan. Before it existed the digest could only
    filter ``AuditEvent.kind__startswith='autonomy_'`` and unpack JSON, which
    is why it never reported cycles at all — only the four event types below.

    An empty list is a legitimate answer for a window that predates the table
    (legacy runs left only ``AuditEvent`` rows, which the caller still scans),
    so absence here is never treated as an error.
    """
    from law_ai.audit.models import AutonomyRun

    rows = AutonomyRun.objects.filter(
        started_at__gte=window_start, started_at__lt=window_end
    ).order_by("started_at")
    return [
        {
            "cycle_id": row.cycle_id,
            "kind": row.kind,
            "status": row.status,
            "duration_ms": float(row.duration_ms or 0.0),
            "summary": row.summary or {},
        }
        for row in rows
    ]


#: How a cycle's ``AutonomyRun.summary`` maps onto the digest's four content
#: sections (BL-20260906-22). Before this, the summary the runner already
#: reported was rendered nowhere, so per-cycle counts had to be reconstructed
#: from an ``AuditEvent`` scan even for windows the table fully covers. Keys are
#: read from the summary itself and from its nested ``result`` (that is where
#: ``run_cycle`` stores the runner's return value).
_SUMMARY_SECTION_KEYS: dict[str, tuple[str, ...]] = {
    "prs": ("prs_opened", "pr_urls", "pr_url"),
    "backlog": ("backlog_ids", "backlog_appended"),
    "docs": ("quarantined", "docs_quarantined"),
    "legalbench": ("legalbench_delta", "legalbench_deltas"),
}


def _as_entries(value: Any) -> list[str]:
    """Render one summary value as digest bullet text."""
    if value is None or value in ("", [], {}):
        return []
    if isinstance(value, dict):
        return [
            f"{key}: {val:+}" if isinstance(val, (int, float)) else f"{key}: {val}"
            for key, val in value.items()
        ]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _fold_cycle_summaries(
    cycles: list[dict[str, Any]], sections: dict[str, list[str]]
) -> None:
    """Merge the runs table's own summaries into the digest sections.

    Additive and de-duplicating: an entry an ``AuditEvent`` already
    contributed is not repeated, and legacy windows with no table rows are
    unaffected — which is why the event scan stays rather than being retired
    outright (BL-20260906-22).
    """
    for cycle in cycles:
        summary = cycle.get("summary") or {}
        if not isinstance(summary, dict):
            continue
        nested = summary.get("result")
        scopes = [summary] + ([nested] if isinstance(nested, dict) else [])
        for section, keys in _SUMMARY_SECTION_KEYS.items():
            for scope in scopes:
                for key in keys:
                    if key not in scope:
                        continue
                    for entry in _as_entries(scope[key]):
                        if entry not in sections[section]:
                            sections[section].append(entry)


def _cycle_counts(summary: dict[str, Any]) -> str:
    """A compact ``k=v`` tail of the numeric counts a runner reported."""
    if not isinstance(summary, dict):
        return ""
    nested = summary.get("result")
    scope: dict[str, Any] = dict(nested) if isinstance(nested, dict) else {}
    scope.update({k: v for k, v in summary.items() if k != "result"})
    counts = [
        f"{key}={value}"
        for key, value in sorted(scope.items())
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return f" — {', '.join(counts)}" if counts else ""


def compose_digest(
    *,
    date: datetime | None = None,
    raise_on_db_error: bool = False,
    window_end: datetime | None = None,
) -> Path:
    """Aggregate the last 24 h of ``autonomy_*`` audit events into a Markdown file.

    Parameters
    ----------
    date:
        Anchor date for the digest window (end = midnight of this date's
        UTC day; defaults to *now*). Pass an explicit value in tests to
        keep output deterministic.
    window_end:
        Explicit end of the digest window, overriding the midnight anchor.
        The default windows on ``[yesterday 00:00, today 00:00)`` UTC, which
        means a digest composed *inside* a 06:00 UTC nightly run contains
        none of that run's own events — exactly the case the CI summary
        needs (BL-20260511-19). Pass ``datetime.now(UTC)`` (the
        ``--window-to-now`` CLI flag) to end the window here instead.
    raise_on_db_error:
        When ``True`` a failed audit-log query propagates instead of
        degrading to an empty digest with an error note. The retrying
        Celery task (``law_ai.core.tasks.compose_digest_task``,
        BL-20260511-23) sets this so a transient
        ``OperationalError``/``InterfaceError`` can be retried rather than
        silently baked into a useless digest file. Default ``False`` keeps
        the never-raises contract the management command relies on.

    Returns
    -------
    pathlib.Path
        Absolute path to the written digest file
        ``<AUTONOMY_DIGEST_DIR>/digest-YYYY-MM-DD.md``.

    Notes
    -----
    * Never raises by default — on DB failure an empty digest with an error
      note is written so the caller always gets a usable path.
    * Every call appends an ``autonomy_digest.composed`` provenance event.
    """
    now: datetime = date or datetime.now(UTC)
    end: datetime = (
        window_end
        if window_end is not None
        else now.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    window_start = end - timedelta(hours=24)
    date_label = end.strftime("%Y-%m-%d")

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

    cycles: list[dict[str, Any]] = []

    try:
        cycles = _digest_cycles(window_start, end)
    except Exception as exc:
        logger.warning("compose_digest AutonomyRun query failed: %s", exc)
        if raise_on_db_error:
            raise
        error_note = f"\n> **Error querying autonomy runs**: {exc}\n"

    try:
        from law_ai.audit.models import AuditEvent

        rows = AuditEvent.objects.filter(
            kind__startswith="autonomy_",
            timestamp__gte=window_start,
            timestamp__lt=end,
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
        if raise_on_db_error:
            raise
        error_note = f"\n> **Error querying audit log**: {exc}\n"

    # ------------------------------------------------------------------
    # Render Markdown
    # ------------------------------------------------------------------
    lines: list[str] = [
        f"# Autonomy Digest — {date_label}",
        f"> Window: {window_start.isoformat()} → {end.isoformat()} UTC",
        "",
    ]
    if error_note:
        lines.append(error_note)

    # BL-20260906-22: the runs table already carries each cycle's own result,
    # so fold it into the four content sections instead of leaving the digest
    # to be reconstructed from an event scan.
    _fold_cycle_summaries(
        cycles,
        {
            "prs": prs_opened,
            "backlog": backlog_appended,
            "docs": docs_quarantined,
            "legalbench": legalbench_deltas,
        },
    )

    lines += [
        "## Autonomy Cycles",
        *(
            [
                f"- `{c['kind']}` {c['status']} "
                f"({c['duration_ms']:.0f} ms, cycle_id `{c['cycle_id']}`)"
                f"{_cycle_counts(c.get('summary') or {})}"
                for c in cycles
            ]
            or ["- *(none)*"]
        ),
        "",
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
            cycles=len(cycles),
            prs=len(prs_opened),
            backlog=len(backlog_appended),
            docs=len(docs_quarantined),
            legalbench=len(legalbench_deltas),
        )
    )
    return digest_path


# ---------------------------------------------------------------------------
# Digest delivery (BL-20260511-05)
# ---------------------------------------------------------------------------
#: Slack's `text` field is capped at 40 000 characters. Leave headroom for the
#: header and the "truncated" footer we append.
_SLACK_TEXT_LIMIT = 38_000


def _redact_webhook(url: str) -> str:
    """Return a non-secret label for a Slack webhook URL.

    The path segments of a Slack webhook *are* the credential, so the audit
    event records only the host plus a short fingerprint — enough to tell two
    workspaces apart, useless to anyone who reads the audit log.
    """
    from hashlib import sha256
    from urllib.parse import urlsplit

    host = urlsplit(url).netloc or "unknown"
    return f"{host}/…{sha256(url.encode('utf-8')).hexdigest()[:8]}"


def _truncate_for_slack(body: str, digest_path: Path) -> str:
    if len(body) <= _SLACK_TEXT_LIMIT:
        return body
    keep = body[:_SLACK_TEXT_LIMIT]
    return f"{keep}\n\n… truncated. Full digest: {digest_path}\n"


def _deliver_slack(body: str, digest_path: Path, webhook: str) -> dict[str, Any]:
    import httpx

    outcome: dict[str, Any] = {"channel": "slack", "target": _redact_webhook(webhook)}
    payload = {"text": _truncate_for_slack(body, digest_path)}
    outcome["truncated"] = len(payload["text"]) != len(body)
    try:
        response = httpx.post(webhook, json=payload, timeout=10.0)
        outcome["status_code"] = response.status_code
        outcome["ok"] = 200 <= response.status_code < 300
        if not outcome["ok"]:
            outcome["error"] = f"HTTP {response.status_code}"
    except Exception as exc:
        logger.warning("digest Slack delivery failed: %s", exc)
        outcome["ok"] = False
        outcome["error"] = repr(exc)
    return outcome


def _deliver_email(
    body: str, date_label: str, recipients: list[str], sender: str
) -> dict[str, Any]:
    from django.core.mail import send_mail

    outcome: dict[str, Any] = {"channel": "email", "recipients": len(recipients)}
    try:
        sent = send_mail(
            subject=f"Law AI autonomy digest — {date_label}",
            message=body,
            from_email=sender,
            recipient_list=recipients,
            fail_silently=False,
        )
        outcome["ok"] = bool(sent)
        outcome["sent"] = int(sent)
        if not sent:
            outcome["error"] = "send_mail reported 0 messages sent"
    except Exception as exc:
        logger.warning("digest email delivery failed: %s", exc)
        outcome["ok"] = False
        outcome["error"] = repr(exc)
    return outcome


def deliver_digest(digest_path: Path | str) -> dict[str, Any]:
    """Push a composed digest to every configured channel (BL-20260511-05).

    Until this existed the ``digest-<date>.md`` file was the only surface, so
    a nightly run that found something interesting only reached a human who
    went looking for it. Two env-driven channels are supported, both off by
    default:

    * ``AUTONOMY_DIGEST_SLACK_WEBHOOK_URL`` — POSTs ``{"text": …}`` to an
      incoming-webhook URL. Slack caps ``text`` at 40 000 characters, so a
      long digest is truncated with a pointer to the file on disk.
    * ``AUTONOMY_DIGEST_EMAIL_TO`` — a comma-separated recipient list sent
      through Django's mail backend (console by default, so a
      mis-configured deployment prints rather than drops).

    Contract, mirroring :func:`compose_digest`:

    * **Never raises.** A dead webhook or a refused SMTP connection is logged
      and reported in the return value; it must not fail the autonomy cycle
      that produced a perfectly good digest file.
    * **No-op when nothing is configured** — the returned dict then says
      ``delivered=0`` and lists no channels.
    * Emits one ``autonomy_digest.delivered`` provenance event carrying the
      per-channel outcome. The webhook URL is a secret and is **never**
      recorded: only ``host/…<8-hex fingerprint>`` reaches the audit log.
    """
    path = Path(digest_path)
    webhook = str(getattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", "") or "")
    raw_recipients = getattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ()) or ()
    recipients = [str(r).strip() for r in raw_recipients if str(r).strip()]
    sender = str(
        getattr(settings, "AUTONOMY_DIGEST_EMAIL_FROM", "law-ai-autonomy@localhost")
    )

    channels: list[dict[str, Any]] = []
    if not webhook and not recipients:
        logger.debug("digest delivery skipped: no channel configured")
    else:
        try:
            body = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("digest delivery could not read %s: %s", path, exc)
            body = ""
            channels.append({"channel": "read", "ok": False, "error": repr(exc)})

        if body:
            date_label = path.stem.removeprefix("digest-")
            if webhook:
                channels.append(_deliver_slack(body, path, webhook))
            if recipients:
                channels.append(_deliver_email(body, date_label, recipients, sender))

    summary: dict[str, Any] = {
        "digest_path": str(path),
        "channels": channels,
        "attempted": len(channels),
        "delivered": sum(1 for c in channels if c.get("ok")),
    }
    _persist(_event("autonomy_digest.delivered", **summary))
    return summary
