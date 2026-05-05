"""Celery application factory (spec 011 FR-11)."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lexgraph.settings.dev")

app = Celery("lexgraph")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # pragma: no cover - debug helper
    return f"Request: {self.request!r}"
