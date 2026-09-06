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

from law_ai.core.settings_proxy import settings_proxy as settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger("law_ai.graphs.runtime")


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


def checkpointer_conn_string(url: str | None = None, schema: str | None = None) -> str:
    """Postgres URL for the checkpointer, pinned to the LangGraph schema.

    ``ensure_checkpointer`` creates a ``langgraph`` schema, but until
    BL-20260811-25 the saver's connection set no ``search_path``, so
    ``setup()`` created every checkpoint table in ``public`` and the isolation
    claim in spec 011 FR-13 was fiction. libpq honours an ``options``
    connection parameter, so ``options=-csearch_path%3D<schema>`` — the ``=``
    must be percent-encoded inside a URL query value — puts the saver in its
    own schema for real.

    Existing deployments already have checkpoint tables in ``public``; those
    rows become invisible after this switch. Either
    ``ALTER TABLE checkpoints SET SCHEMA langgraph`` (and the sibling tables)
    once, or accept a fresh start — in-flight threads are resumable state, not
    system of record.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    # The asyncpg URL we ship is fine for SQLAlchemy but the checkpointer
    # uses psycopg, so strip the driver suffix when present.
    raw = (url if url is not None else settings.POSTGRES_URL).replace("+asyncpg", "")
    target = schema or str(
        getattr(settings, "LANGGRAPH_CHECKPOINTER_SCHEMA", "langgraph")
    )
    if not target:
        return raw
    parts = urlsplit(raw)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    # Never clobber an operator-supplied `options`.
    if any(k == "options" for k, _ in query):
        return raw
    query.append(("options", f"-csearch_path={target}"))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _build_postgres_saver() -> AbstractAsyncContextManager[BaseCheckpointSaver]:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise CheckpointerUnavailableError(
            "langgraph-checkpoint-postgres not installed — add the local-ai extra"
        ) from exc
    return AsyncPostgresSaver.from_conn_string(checkpointer_conn_string())


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
