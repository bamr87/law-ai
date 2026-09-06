"""Test settings — in-memory channel layer + eager Celery + SQLite by default.

Full test isolation: no real Redis, no real Postgres, no
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

# In-process cache for the suite (BL-20260810-15): no Redis, and a fresh
# namespace per process so a probe verdict cannot leak between test runs.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "law-ai-tests",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# BL-20260811-07: OFF for the suite. pytest-django wraps each django_db test
# in a transaction that a second thread's connection cannot see, so an
# offloaded insert would either block or write into a different snapshot.
# The tests that exercise the offload turn it on explicitly with
# `transaction=True`.
AUDIT_DB_THREAD_OFFLOAD = False

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

# Spec 050: the same lockout for the xAI tier. Blanking the seed tokens is not
# enough on its own — a developer who has run `make xai-login` has a live
# credentials *file*, and the store falls back to it. Point the path at a
# location that cannot exist so `is_configured()` is False in the suite no
# matter what is on the developer's disk, and aim both base URLs at a closed
# port so even a test that forces a credential in cannot reach xAI.
XAI_ACCESS_TOKEN = ""
XAI_REFRESH_TOKEN = ""
XAI_CREDENTIALS_PATH = "/nonexistent/law-ai-test/xai-credentials.json"
XAI_AUTH_BASE_URL = "http://127.0.0.1:1"
XAI_BASE_URL = "http://127.0.0.1:1/v1"

# Throttling is effectively disabled for the suite (BL-20260810-11): the API
# tests fire many requests at the LLM-scoped endpoints in well under a
# minute and would otherwise trip the production 20/min limit. Tests that
# assert throttling behaviour override this rate explicitly.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "llm": "100000/min",
        "llm_keyed": "100000/min",
        "audit": "100000/min",
        "audit_keyed": "100000/min",
    },
}


# BL-20260429-16: the ops dashboard push is a production affordance. Left on,
# every agent call in the suite would schedule a channel-layer write nothing
# asserts on; the tests that cover it enable it explicitly.
AGENT_OPS_PUSH_ENABLED = False


# BL-20260811-14: pin the agent-stream replay buffer to its in-process
# fallback. REDIS_URL still points at the dev container here, and a shared
# buffer would let one test's events reach another's assertions.
AGENT_STREAM_REPLAY_URL = ""
