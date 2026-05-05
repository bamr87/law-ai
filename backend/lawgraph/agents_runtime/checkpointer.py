"""Idempotent migration entry point for the LangGraph checkpointer schema.

Called from ``app.main`` lifespan so a fresh Postgres self-heals on backend
boot. Failures are logged but do not crash startup — the LangGraph routes
will surface a clear error when invoked instead.
"""

from __future__ import annotations

import logging

from lawgraph.agents_runtime.graphs.runtime import (
    CheckpointerUnavailableError,
    build_checkpointer,
)
from lawgraph.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("lawgraph.db.checkpointer")


async def ensure_schema() -> None:
    """Run ``setup()`` on the configured saver if it supports it.

    Safe to call multiple times: ``AsyncPostgresSaver.setup()`` issues
    ``CREATE TABLE IF NOT EXISTS`` for every table it manages.
    """
    if settings.LANGGRAPH_CHECKPOINTER == "memory":
        return
    try:
        cm = build_checkpointer()
    except CheckpointerUnavailableError as exc:
        logger.warning("checkpointer schema not initialized: %s", exc)
        return
    try:
        async with cm as saver:
            setup = getattr(saver, "setup", None)
            if setup is None:
                logger.info(
                    "checkpointer %s has no setup() — skipping migration",
                    type(saver).__name__,
                )
                return
            await setup()
            logger.info("checkpointer schema ready (%s)", type(saver).__name__)
    except Exception as exc:  # pragma: no cover - defensive log-only
        logger.warning("checkpointer setup failed: %s", exc)
