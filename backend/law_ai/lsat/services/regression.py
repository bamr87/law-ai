"""Per-item cross-check regression tracking (BL-20260527-06).

The LegalBench harness answers "did the *agent* get worse on the benchmark";
this module answers the LSAT-flavoured sibling: "did the chain's blind solve
of *this particular bank item* change over time". Every fresh
:func:`law_ai.lsat.services.crosscheck.cross_check` verdict is an
``lsat_cross_check`` audit event carrying the question id, the model, the
prompt version and the agree/disagree outcome, so the audit log *is* the time
series — the response cache keeps only the latest verdict per question and
cannot see a flip.

A question **regressed** when its earliest stored verdict agreed with the key
and its latest one does not; it **recovered** on the opposite flip. Both lists
are surfaced on ``/api/lsat/validation`` next to the deterministic findings so
a reviewer sees the drift where they already look. Cached re-reads and
degraded (no provider) verdicts are ignored: neither is a new solve.

Events are read from the ``AuditEvent`` table when a sync database context is
available and from the JSONL audit store otherwise, de-duplicated by
``(question_id, timestamp)`` — the same event is written to both, and the
table outlives the JSONL ring rotation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.provenance import _in_async_context
from law_ai.lsat.services.bank import load_bank

logger = logging.getLogger("law_ai.lsat.regression")

EVENT_KIND = "lsat_cross_check"

DEFAULT_WINDOW = 5000

#: How far back a verdict may sit and still take part in the flip comparison
#: (BL-20260905-59). Without it a long-lived bank compares a verdict from
#: months ago — a different model, a different prompt version — against
#: today's and calls the difference a regression. ``None`` disables the
#: cutoff and restores the all-time comparison.
DEFAULT_SINCE_DAYS: int | None = 90


def _is_fresh_verdict(ev: dict[str, Any]) -> bool:
    return (
        ev.get("type") == EVENT_KIND
        and bool(ev.get("used_llm"))
        and not ev.get("cached")
        and isinstance(ev.get("question_id"), str)
        and isinstance(ev.get("agree"), bool)
        and isinstance(ev.get("timestamp"), str)
    )


def _db_events(window: int) -> list[dict[str, Any]]:
    """Newest ``window`` cross-check rows from ``AuditEvent`` (sync only)."""
    if _in_async_context():
        return []
    try:
        from law_ai.audit.models import AuditEvent

        rows = AuditEvent.objects.filter(kind=EVENT_KIND).order_by("-timestamp")[
            :window
        ]
        return [dict(r.payload) for r in rows if isinstance(r.payload, dict)]
    except Exception as exc:  # DB down / unmigrated — JSONL is the record
        logger.debug("regression: AuditEvent read skipped (%s)", exc)
        return []


def _cutoff(since_days: int | None) -> datetime | None:
    if since_days is None:
        return None
    return datetime.now(UTC) - timedelta(days=max(0, since_days))


def _within(timestamp: str, cutoff: datetime | None) -> bool:
    """Is this verdict recent enough to compare? Unparseable dates are kept."""
    if cutoff is None:
        return True
    try:
        stamp = datetime.fromisoformat(timestamp)
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp >= cutoff


def cross_check_history(
    window: int = DEFAULT_WINDOW,
    *,
    since_days: int | None = DEFAULT_SINCE_DAYS,
) -> dict[str, list[dict[str, Any]]]:
    """Fresh verdicts per question id, oldest first.

    Each verdict is ``{timestamp, agree, model_choice, bank_choice, model,
    prompt_version}``. Verdicts older than ``since_days`` are left out
    entirely, so a stale first verdict cannot anchor a comparison against
    today's (BL-20260905-59); pass ``since_days=None`` for the whole history.
    """
    cutoff = _cutoff(since_days)
    seen: set[tuple[str, str]] = set()
    per_question: dict[str, list[dict[str, Any]]] = {}
    for ev in [*audit_store.tail(window), *_db_events(window)]:
        if not _is_fresh_verdict(ev) or not _within(ev["timestamp"], cutoff):
            continue
        key = (ev["question_id"], ev["timestamp"])
        if key in seen:
            continue
        seen.add(key)
        per_question.setdefault(ev["question_id"], []).append(
            {
                "timestamp": ev["timestamp"],
                "agree": ev["agree"],
                "model_choice": ev.get("model_choice"),
                "bank_choice": ev.get("bank_choice"),
                "model": ev.get("model"),
                "prompt_version": ev.get("prompt_version"),
            }
        )
    for verdicts in per_question.values():
        verdicts.sort(key=lambda v: v["timestamp"])
    return per_question


def regression_report(
    window: int = DEFAULT_WINDOW,
    *,
    section: str | None = None,
    since_days: int | None = DEFAULT_SINCE_DAYS,
) -> dict[str, Any]:
    """Flag bank items whose blind-solve verdict flipped over the window.

    Returns ``{window, since_days, tracked, regressed, recovered}`` where
    ``tracked`` is the number of questions with at least one fresh verdict in
    the window and each flip row carries the earliest and latest verdict so
    the reviewer can see which model/prompt produced each side.

    ``window`` bounds how many *events* are read; ``since_days`` bounds how
    *old* a verdict may be and still be compared (BL-20260905-59). A verdict
    from months ago was produced by a different model and prompt version, so
    calling today's disagreement with it a regression is noise, not signal.
    """
    bank = load_bank()
    regressed: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    tracked = 0
    for qid, verdicts in sorted(
        cross_check_history(window, since_days=since_days).items()
    ):
        q = bank.get(qid)
        if q is None or (section is not None and q.section != section):
            continue
        tracked += 1
        first, latest = verdicts[0], verdicts[-1]
        if first["agree"] == latest["agree"]:
            continue
        row = {
            "question_id": qid,
            "section": q.section,
            "verdicts": len(verdicts),
            "first": first,
            "latest": latest,
        }
        (regressed if first["agree"] else recovered).append(row)
    return {
        "window": window,
        "since_days": since_days,
        "tracked": tracked,
        "regressed": regressed,
        "recovered": recovered,
    }


__all__ = [
    "DEFAULT_SINCE_DAYS",
    "DEFAULT_WINDOW",
    "EVENT_KIND",
    "cross_check_history",
    "regression_report",
]
