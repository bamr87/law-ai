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

# Spec 034: hard-disable every LLM provider for the suite. This module's
# "no network" promise is load-bearing in two directions now that Claude is
# the default runtime:
#   * A developer with CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY exported (or
#     in .env, which django-environ reads) would otherwise have `make test`
#     issue real, billed API calls.
#   * A reachable local Ollama would otherwise turn unit tests into multi-second
#     integration runs against a live model.
# The chain order is deliberately left at the production default so tests
# exercise real routing; every tier simply has nowhere to go. Tests that need a
# provider to answer patch `llm.agenerate` (or set a credential via the
# `settings` fixture).
CLAUDE_CODE_OAUTH_TOKEN = ""
ANTHROPIC_API_KEY = ""
OLLAMA_BASE_URL = "http://127.0.0.1:1"  # closed port — fails instantly

# Throttling is effectively disabled for the suite (BL-20260810-11): the API
# tests fire many requests at the LLM-scoped endpoints in well under a
# minute and would otherwise trip the production 20/min limit. Tests that
# assert throttling behaviour override this rate explicitly.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"llm": "100000/min"},
}

# Spec 037: the suite must not export traces. `.env` sets
# PHOENIX_COLLECTOR_ENDPOINT for the compose stack, and django-environ reads
# it here too, so without this line `CoreConfig.ready()` registers a live
# tracer provider and every test run ships spans into the Phoenix container —
# polluting the trace store and (post-FR-7) potentially test prompt content.
# It also makes AC-5 unobservable: "no global tracer provider is set" cannot
# be asserted in a process that set one at boot.
PHOENIX_COLLECTOR_ENDPOINT = None
PHOENIX_TRACE_CONTENT = False
