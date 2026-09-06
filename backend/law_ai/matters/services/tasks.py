"""Deadline tracking for the action stage (BL-20260817-02).

The journey's action stage could only record what a user chose to log as an
artifact — there was nowhere to put "answer due 14 October". These are the
two pieces that turn a to-do list into a deadline surface:

* :func:`calendar_for_user` — every open dated task the caller owns, across
  matters, grouped into overdue / today / upcoming, because a practitioner
  works several matters at once and no per-matter list can answer "what is due
  this week".
* :func:`sweep_due_reminders` — the Celery-beat tick that emits one
  ``matter.task_reminder`` provenance event per newly-due task and, only when
  ``MATTER_TASK_EMAIL_REMINDERS`` is on, sends mail through Django's
  configured backend. In-app first, email behind a flag: a reminder channel
  that surprises a user with mail about a client matter is worse than no
  reminder at all.

Spec 036 NG1 stands: due dates are user-entered. Nothing here computes a
court deadline from a rule of procedure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings

from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.matters.tasks")

#: How long before a due date a reminder fires.
DEFAULT_LEAD_HOURS = 24

#: Cap per sweep so a large backlog cannot monopolise a worker.
SWEEP_LIMIT = 100


def _open_dated_tasks(user: Any) -> Any:
    from law_ai.matters.models import MatterTask

    return (
        MatterTask.objects.select_related("matter")
        .filter(
            matter__owner=user,
            matter__archived_at__isnull=True,
            archived_at__isnull=True,
            status=MatterTask.STATUS_OPEN,
            due_at__isnull=False,
        )
        .order_by("due_at")
    )


def calendar_for_user(
    user: Any, *, days: int = 30, now: datetime | None = None
) -> dict[str, Any]:
    """Open dated tasks in the window, bucketed by urgency."""
    moment = now or datetime.now(UTC)
    horizon = moment + timedelta(days=days)
    end_of_today = moment.replace(hour=23, minute=59, second=59, microsecond=0)

    overdue: list[dict[str, Any]] = []
    today: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    for task in _open_dated_tasks(user).filter(due_at__lte=horizon)[:200]:
        row = task.as_payload()
        row["matter_slug"] = task.matter.slug
        row["matter_name"] = task.matter.name
        if task.due_at < moment:
            row["overdue_days"] = round(
                (moment - task.due_at).total_seconds() / 86400.0, 2
            )
            overdue.append(row)
        elif task.due_at <= end_of_today:
            today.append(row)
        else:
            upcoming.append(row)
    return {
        "window_days": days,
        "generated_at": moment.isoformat(),
        "overdue": overdue,
        "today": today,
        "upcoming": upcoming,
        "count": len(overdue) + len(today) + len(upcoming),
    }


def _send_reminder_email(task: Any) -> bool:
    """Best-effort mail through Django's backend. Never raises."""
    owner = task.matter.owner
    address = getattr(owner, "email", "")
    if not address:
        return False
    try:
        from django.core.mail import send_mail

        due = task.due_at.isoformat() if task.due_at else "soon"
        send_mail(
            subject=f"[Law AI] {task.title} is due {due}",
            message=(
                f"Matter: {task.matter.name}\n"
                f"Task: {task.title}\n"
                f"Due: {due}\n\n"
                f"{task.detail}\n"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[address],
            fail_silently=True,
        )
        return True
    except Exception:  # pragma: no cover - mail backend misconfigured
        logger.warning("task reminder email failed", exc_info=True)
        return False


def sweep_due_reminders(
    *, now: datetime | None = None, lead_hours: int | None = None
) -> list[dict[str, Any]]:
    """Emit reminders for tasks entering their lead window. Idempotent.

    ``reminded_at`` is the guard: a task is reminded once per due date, and
    rescheduling it (which clears the field) earns a fresh reminder.
    """
    from law_ai.matters.models import MatterTask

    moment = now or datetime.now(UTC)
    lead = timedelta(
        hours=(
            lead_hours
            if lead_hours is not None
            else int(
                getattr(settings, "MATTER_TASK_REMINDER_LEAD_HOURS", DEFAULT_LEAD_HOURS)
            )
        )
    )
    due_rows = list(
        MatterTask.objects.select_related("matter", "matter__owner").filter(
            archived_at__isnull=True,
            matter__archived_at__isnull=True,
            status=MatterTask.STATUS_OPEN,
            due_at__isnull=False,
            due_at__lte=moment + lead,
            reminded_at__isnull=True,
        )[:SWEEP_LIMIT]
    )
    emailed_enabled = bool(getattr(settings, "MATTER_TASK_EMAIL_REMINDERS", False))
    out: list[dict[str, Any]] = []
    for task in due_rows:
        emailed = _send_reminder_email(task) if emailed_enabled else False
        task.reminded_at = moment
        task.save(update_fields=["reminded_at"])
        provenance.log_event(
            "matter.task_reminder",
            {
                "matter_id": task.matter_id,
                "task_id": task.pk,
                "title": task.title,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "emailed": emailed,
            },
        )
        out.append({"task_id": task.pk, "emailed": emailed})
    if out:
        logger.info("matter task reminders: %d emitted", len(out))
    return out


__all__ = [
    "DEFAULT_LEAD_HOURS",
    "calendar_for_user",
    "sweep_due_reminders",
]
