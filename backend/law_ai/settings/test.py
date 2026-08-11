"""Test settings — in-memory channel layer + eager Celery + SQLite by default.

Mirrors the FastAPI test isolation: no real Redis, no real Postgres, no
network. Override ``DATABASE_URL`` to run integration tests against a real
Postgres container.
"""

from __future__ import annotations

import os

# Default to SQLite if no DATABASE_URL was provided.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.sqlite3")

from .base import *  # noqa: F403

DEBUG = False
ENVIRONMENT = "test"
ALLOWED_HOSTS = ["*"]

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Throttling is effectively disabled for the suite (BL-20260810-11): the API
# tests fire many requests at the LLM-scoped endpoints in well under a
# minute and would otherwise trip the production 20/min limit. Tests that
# assert throttling behaviour override this rate explicitly.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"llm": "100000/min"},
}
