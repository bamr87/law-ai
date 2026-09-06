"""Per-learner attempt history and spaced repetition (BL-20260503-05).

``/api/lsat/stats`` was an instance-wide readout of the JSONL audit log: it
could tell you how many questions *this box* had graded, never how **you**
were doing, and it had no notion of what to practise next. With accounts
(spec 036 T-002) an attempt can be attributed, so this module answers the two
questions the readout could not:

* **How is this learner doing?** — overall and per-section accuracy, the
  assisted/unassisted split (a hinted correct answer is not the same skill as
  an unhinted one), and accuracy over time so improvement is visible.
* **What should they practise next?** — a Leitner-style review queue. Each
  question the learner has attempted sits in a box equal to its current
  streak of consecutive correct answers; a wrong answer resets to box 0 and
  is due immediately, box *k* comes back in ``2^(k-1)`` days. That is the
  cheapest schedule that still has the two properties that matter: recently
  missed material returns first, and material you keep getting right recedes.

Everything here is pure ORM aggregation over :class:`LsatAttempt`; the
anonymous path in the view still reads the audit log and is untouched.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("law_ai.lsat.attempts")

#: How many due items the queue returns by default.
DEFAULT_QUEUE_LIMIT = 20

#: Box 0 (last answer wrong) is due immediately; box k is due 2^(k-1) days
#: after the last attempt. Capped so a long streak does not overflow into a
#: date nobody will ever reach.
MAX_BOX = 6


def interval_days(streak: int) -> int:
    """Days until a question with ``streak`` consecutive correct answers returns."""
    if streak <= 0:
        return 0
    return int(2 ** (min(streak, MAX_BOX) - 1))


def record_attempt(
    user: Any,
    *,
    question_id: str,
    section: str,
    difficulty: str = "",
    choice: str = "",
    correct: bool,
    hints_used: int = 0,
    shuffled: bool = False,
    concepts: list[str] | None = None,
) -> Any | None:
    """Persist one graded answer. Best-effort: never fails a grade response.

    A learner who just answered a question must get their verdict even if the
    database is unreachable — the audit event has already been written, so
    losing the row costs statistics, not correctness.
    """
    from law_ai.lsat.models import LsatAttempt

    try:
        return LsatAttempt.objects.create(
            user=user,
            question_id=question_id,
            section=section or "",
            difficulty=difficulty or "",
            choice=choice or "",
            correct=bool(correct),
            hints_used=int(hints_used or 0),
            shuffled=bool(shuffled),
            concepts=list(concepts or []),
        )
    except Exception:  # pragma: no cover - storage hiccup must not break UX
        logger.warning("failed to persist LSAT attempt", exc_info=True)
        return None


def record_writing_attempt(
    user: Any,
    *,
    prompt_id: str,
    rubric_id: str = "",
    weighted_band: float | None,
    criteria: dict[str, Any] | None = None,
    response_chars: int = 0,
    model: str = "",
    prompt_version: str = "",
    degraded: bool = False,
) -> Any | None:
    """Persist one evaluated essay. Best-effort, like :func:`record_attempt`.

    BL-20260906-18: writing evaluations used to land in the JSONL audit log
    alone, so a signed-in learner's writing totals were everyone's.
    """
    from law_ai.lsat.models import LsatWritingAttempt

    try:
        return LsatWritingAttempt.objects.create(
            user=user,
            prompt_id=prompt_id,
            rubric_id=rubric_id or "",
            weighted_band=weighted_band,
            criteria=dict(criteria or {}),
            response_chars=int(response_chars or 0),
            model=model or "",
            prompt_version=prompt_version or "",
            degraded=bool(degraded),
        )
    except Exception:  # pragma: no cover - storage hiccup must not break UX
        logger.warning("failed to persist LSAT writing attempt", exc_info=True)
        return None


def writing_stats(user: Any) -> dict[str, Any]:
    """This learner's Argumentative Writing practice, oldest first.

    Same shape ``_fold_writing`` builds from the audit tail (BL-20260831-27),
    so the response does not change when the reading does — only whose essays
    it counts.
    """
    from law_ai.lsat.models import LsatWritingAttempt

    rows = list(
        LsatWritingAttempt.objects.filter(user=user)
        .order_by("created_at")
        .values(
            "prompt_id",
            "weighted_band",
            "degraded",
            "model",
            "prompt_version",
        )
    )
    bands = [
        float(r["weighted_band"])
        for r in rows
        if isinstance(r["weighted_band"], (int, float))
    ]
    by_prompt: dict[str, int] = {}
    for row in rows:
        pid = str(row["prompt_id"])
        by_prompt[pid] = by_prompt.get(pid, 0) + 1
    latest = rows[-1] if rows else {}
    return {
        "attempts": len(rows),
        "by_prompt": by_prompt,
        "latest_band": bands[-1] if bands else None,
        "best_band": max(bands) if bands else None,
        "band_trend": [round(b, 4) for b in bands],
        "degraded": sum(1 for r in rows if r["degraded"] is True),
        "model": latest.get("model") or None,
        "prompt_version": latest.get("prompt_version") or None,
    }


def _bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    assisted = sum(1 for r in rows if r["hints_used"])
    return {
        "attempts": attempts,
        "correct": correct,
        "accuracy": round(correct / attempts, 4) if attempts else 0.0,
        "assisted": assisted,
        "unassisted": attempts - assisted,
    }


def _accuracy_over_time(
    rows: list[dict[str, Any]], buckets: int = 5
) -> list[dict[str, Any]]:
    """Split the learner's history into equal slices, oldest first.

    Equal *counts* rather than equal calendar spans: a learner who studied
    hard for a week and then paused for a month wants to see the shape of
    their practice, not a row of empty days.
    """
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: r["created_at"])
    size = max(1, len(ordered) // buckets)
    out: list[dict[str, Any]] = []
    for start in range(0, len(ordered), size):
        chunk = ordered[start : start + size]
        if not chunk:
            continue
        summary = _bucket(chunk)
        summary["from"] = chunk[0]["created_at"].isoformat()
        summary["to"] = chunk[-1]["created_at"].isoformat()
        out.append(summary)
    # A trailing remainder smaller than the slice merges into the last full
    # one so the final point is not a noisy one-attempt spike.
    if len(out) > buckets and len(out) >= 2:
        tail = out.pop()
        last = out[-1]
        merged = {
            "attempts": last["attempts"] + tail["attempts"],
            "correct": last["correct"] + tail["correct"],
            "assisted": last["assisted"] + tail["assisted"],
        }
        merged["unassisted"] = merged["attempts"] - merged["assisted"]
        merged["accuracy"] = round(merged["correct"] / merged["attempts"], 4)
        merged["from"] = last["from"]
        merged["to"] = tail["to"]
        out[-1] = merged
    return out


def _streak_state(rows: list[dict[str, Any]]) -> tuple[int, datetime, dict[str, Any]]:
    """Consecutive trailing correct answers, the last attempt time, and it."""
    ordered = sorted(rows, key=lambda r: r["created_at"])
    last = ordered[-1]
    streak = 0
    for row in reversed(ordered):
        if not row["correct"]:
            break
        streak += 1
    return streak, last["created_at"], last


def review_queue(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_QUEUE_LIMIT,
) -> list[dict[str, Any]]:
    """Questions due for review, most overdue first (Leitner boxes).

    ``rows`` are the learner's attempts as dicts; grouping happens here so
    the caller can feed either an ORM ``.values()`` result or a test list.
    """
    moment = now or datetime.now(UTC)
    by_question: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_question.setdefault(str(row["question_id"]), []).append(row)

    due: list[dict[str, Any]] = []
    for question_id, attempts in by_question.items():
        streak, last_at, last = _streak_state(attempts)
        due_at = last_at + timedelta(days=interval_days(streak))
        if due_at > moment:
            continue
        due.append(
            {
                "question_id": question_id,
                "section": last.get("section") or "",
                "difficulty": last.get("difficulty") or "",
                "concepts": list(last.get("concepts") or []),
                "streak": streak,
                "box": min(streak, MAX_BOX),
                "attempts": len(attempts),
                "last_attempt_at": last_at.isoformat(),
                "due_at": due_at.isoformat(),
                "overdue_days": round((moment - due_at).total_seconds() / 86400.0, 3),
                # A question the learner has never got right is the reason the
                # queue exists; say so rather than making the UI infer it.
                "reason": "missed" if streak == 0 else "spaced-review",
            }
        )
    due.sort(key=lambda item: (-item["overdue_days"], item["question_id"]))
    return due[:limit]


def user_stats(
    user: Any,
    *,
    section: str | None = None,
    now: datetime | None = None,
    queue_limit: int = DEFAULT_QUEUE_LIMIT,
) -> dict[str, Any]:
    """Per-learner stats in the same shape the anonymous path returns.

    ``section`` filters the *totals* only: the review queue always spans
    every section, because narrowing "what should I practise" to the tab the
    learner happens to be looking at hides the work they are avoiding.
    """
    from law_ai.lsat.models import LsatAttempt

    fields = (
        "question_id",
        "section",
        "difficulty",
        "correct",
        "hints_used",
        "concepts",
        "created_at",
    )
    all_rows = [dict(r) for r in LsatAttempt.objects.filter(user=user).values(*fields)]
    rows = [r for r in all_rows if not section or r["section"] == section]

    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_section.setdefault(str(row["section"] or "?"), []).append(row)

    body = _bucket(rows)
    body["by_section"] = {sec: _bucket(group) for sec, group in by_section.items()}
    body["accuracy_over_time"] = _accuracy_over_time(rows)
    body["review_queue"] = review_queue(all_rows, now=now, limit=queue_limit)
    body["scope"] = "user"
    body["questions_seen"] = len({r["question_id"] for r in all_rows})
    return body


__all__ = [
    "DEFAULT_QUEUE_LIMIT",
    "MAX_BOX",
    "interval_days",
    "record_attempt",
    "record_writing_attempt",
    "review_queue",
    "user_stats",
    "writing_stats",
]
