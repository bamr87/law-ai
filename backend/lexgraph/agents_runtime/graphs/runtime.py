"""LangGraph runtime helpers (spec 010 FR-2).

Picks a ``BaseCheckpointSaver`` based on ``settings.LANGGRAPH_CHECKPOINTER``:

* ``postgres`` — durable, recommended default (requires the ``local-ai``
  extra: ``pip install -e ".[dev,local-ai]"``).
* ``redis``   — fast queues for high-throughput agents.
* ``memory``  — in-process only; safe for unit tests and ad-hoc REPL work.

All heavy imports live inside the factory so the bare backend (no
``local-ai`` extra installed) still boots and serves the legacy CrewAI
flows.
"""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from lawgraph.core.settings_proxy import settings_proxy as settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger("lawgraph.graphs.runtime")


class CheckpointerUnavailableError(RuntimeError):
    """Raised when the configured checkpointer backend cannot be loaded.

    Most commonly this means the ``local-ai`` extra is not installed:

        pip install -e ".[dev,local-ai]"
    """


def _build_memory_saver() -> BaseCheckpointSaver:
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise CheckpointerUnavailableError(
            'langgraph not installed — run `pip install -e ".[dev,local-ai]"`'
        ) from exc
    return MemorySaver()


def _build_postgres_saver() -> AbstractAsyncContextManager[BaseCheckpointSaver]:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise CheckpointerUnavailableError(
            "langgraph-checkpoint-postgres not installed — add the local-ai extra"
        ) from exc
    # The asyncpg URL we ship is fine for SQLAlchemy but the checkpointer
    # uses psycopg, so strip the driver suffix when present.
    url = settings.POSTGRES_URL.replace("+asyncpg", "")
    return AsyncPostgresSaver.from_conn_string(url)


def _build_redis_saver() -> AbstractAsyncContextManager[BaseCheckpointSaver]:
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    except ImportError as exc:
        raise CheckpointerUnavailableError(
            "langgraph-checkpoint-redis not installed — add the local-ai extra"
        ) from exc
    return AsyncRedisSaver.from_conn_string(settings.REDIS_URL)


def build_checkpointer(kind: str | None = None) -> Any:
    """Return a checkpointer for the configured backend.

    For ``postgres`` and ``redis`` the return value is an *async context
    manager* yielding the saver — callers should ``async with build_checkpointer()
    as saver:`` to manage the underlying connection. ``memory`` returns the
    saver directly (no resources to release).

    The asymmetry mirrors the upstream LangGraph API and keeps connection
    lifecycles explicit. Pass ``kind`` to override ``settings.LANGGRAPH_CHECKPOINTER``
    (test-only escape hatch).
    """
    chosen = (kind or settings.LANGGRAPH_CHECKPOINTER).lower()
    if chosen == "memory":
        logger.info("checkpointer: using in-process MemorySaver (test mode)")
        return _build_memory_saver()
    if chosen == "redis":
        logger.info("checkpointer: using AsyncRedisSaver at %s", settings.REDIS_URL)
        return _build_redis_saver()
    if chosen == "postgres":
        logger.info("checkpointer: using AsyncPostgresSaver")
        return _build_postgres_saver()
    raise ValueError(
        f"unknown LANGGRAPH_CHECKPOINTER={chosen!r} (expected postgres|redis|memory)"
    )
