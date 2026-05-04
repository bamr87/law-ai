"""LexGraph AI — Django backend (spec 011, ADR 0001).

Importing this package eagerly loads the Celery app so the ``@shared_task``
decorator works for all apps that import ``celery.shared_task``.
"""
from __future__ import annotations

# Spec 011 FR-11: ensure Celery app is loaded when Django starts.
from .celery import app as celery_app

__all__ = ("celery_app",)
