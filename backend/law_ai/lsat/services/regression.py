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
from typing import Any

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.provenance import _in_async_context
from law_ai.lsat.services.bank import load_bank

logger = logging.getLogger("law_ai.lsat.regression")

EVENT_KIND = "lsat_cross_check"

DEFAULT_WINDOW = 5000


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


def cross_check_history(
    window: int = DEFAULT_WINDOW,
) -> dict[str, list[dict[str, Any]]]:
    """Fresh verdicts per question id, oldest first.

    Each verdict is ``{timestamp, agree, model_choice, bank_choice, model,
    prompt_version}``.
    """
    seen: set[tuple[str, str]] = set()
    per_question: dict[str, list[dict[str, Any]]] = {}
    for ev in [*audit_store.tail(window), *_db_events(window)]:
        if not _is_fresh_verdict(ev):
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
    window: int = DEFAULT_WINDOW, *, section: str | None = None
) -> dict[str, Any]:
    """Flag bank items whose blind-solve verdict flipped over the window.

    Returns ``{window, tracked, regressed, recovered}`` where ``tracked`` is
    the number of questions with at least one fresh verdict and each flip
    row carries the earliest and latest verdict so the reviewer can see which
    model/prompt produced each side.
    """
    bank = load_bank()
    regressed: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    tracked = 0
    for qid, verdicts in sorted(cross_check_history(window).items()):
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
        "tracked": tracked,
        "regressed": regressed,
        "recovered": recovered,
    }


__all__ = ["DEFAULT_WINDOW", "EVENT_KIND", "cross_check_history", "regression_report"]
