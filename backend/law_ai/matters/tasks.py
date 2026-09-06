"""Celery entry points for matters (BL-20260817-02).

One task, one job: walk the tasks whose user-entered due date has entered the
reminder window and emit a reminder for each. The sweep is idempotent
(``reminded_at`` short-circuits), so running it often costs an empty query and
never double-notifies.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger("law_ai.matters.tasks")


# Celery's decorator is untyped, so mypy --strict would call every task
# untyped; the repo's other task modules carry the same (baselined) error.
@shared_task(  # type: ignore[untyped-decorator]
    name="law_ai.matters.sweep_task_reminders", ignore_result=True
)
def sweep_task_reminders() -> dict[str, Any]:
    """Emit reminders for matter tasks entering their lead window."""
    from law_ai.matters.services.tasks import sweep_due_reminders

    results = sweep_due_reminders()
    return {
        "reminded": len(results),
        "emailed": sum(1 for r in results if r.get("emailed")),
    }


__all__ = ["sweep_task_reminders"]
