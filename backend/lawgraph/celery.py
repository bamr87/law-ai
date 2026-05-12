"""Celery application factory (spec 011 FR-11)."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lawgraph.settings.dev")

app = Celery("lawgraph")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Spec 018 T-009: Autonomy beat schedule (all disabled when AUTONOMY_ENABLED=False).
# Operators activate by setting AUTONOMY_ENABLED=true in their environment.
#
# NOTE: The autonomy tasks are routed to the "autonomy" queue. The worker
# container must include "-Q autonomy,celery" (or use CELERY_TASK_ROUTES)
# to consume these entries. See docker-compose.yml worker command.
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    # Pillar B — corpus sweep every 6h (constitution §12 invariant I4).
    "autonomy-content-sweep": {
        "task": "lawgraph.core.tasks.autonomy_cycle",
        "schedule": 6 * 3600,  # every 6 hours (seconds)
        "kwargs": {"kind": "corpus_growth", "budget": 25},
        "options": {"queue": "autonomy"},
    },
    # Pillar A — nightly test synthesis (06:00 UTC).
    "autonomy-nightly-tests": {
        "task": "lawgraph.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {"kind": "test_pillar"},
        "options": {"queue": "autonomy"},
    },
    # Pillar C — daily autonomy digest (07:00 UTC, spec 018 T-010).
    "autonomy-daily-digest": {
        "task": "lawgraph.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=7, minute=0),
        "kwargs": {"kind": "digest"},
        "options": {"queue": "autonomy"},
    },
}
app.conf.beat_schedule_filename = "celerybeat-schedule"


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # pragma: no cover - debug helper
    return f"Request: {self.request!r}"
