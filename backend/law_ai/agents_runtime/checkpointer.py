"""Idempotent migration entry point for the LangGraph checkpointer schema.

Called by ``manage.py ensure_checkpointer``, which compose runs on backend
boot (``docker-compose.yml``) and ``make migrate`` runs locally, so a fresh
Postgres self-heals. :func:`ensure_schema` never raises: it reports what
happened and lets the caller decide whether a failure is fatal
(``LANGGRAPH_CHECKPOINTER_REQUIRED``) — BL-20260811-27.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from law_ai.agents_runtime.graphs.runtime import (
    CheckpointerUnavailableError,
    build_checkpointer,
)
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.db.checkpointer")


@dataclass(frozen=True)
class SchemaStatus:
    """Outcome of one :func:`ensure_schema` call.

    ``state`` is one of ``ok`` (tables created/verified), ``skipped`` (memory
    backend, or a saver with no ``setup()``) or ``error``. ``detail`` carries
    the human-readable reason; ``error`` the exception when there was one.
    """

    state: str
    detail: str = ""
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.state != "error"


async def ensure_schema() -> SchemaStatus:
    """Run ``setup()`` on the configured saver if it supports it.

    Safe to call multiple times: ``AsyncPostgresSaver.setup()`` issues
    ``CREATE TABLE IF NOT EXISTS`` for every table it manages. Never raises —
    a broken ``POSTGRES_URL`` comes back as ``state="error"`` so the caller
    can log loudly or fail fast rather than discovering it on first use.
    """
    if settings.LANGGRAPH_CHECKPOINTER == "memory":
        return SchemaStatus("skipped", "memory checkpointer has no schema")
    try:
        cm = build_checkpointer()
    except CheckpointerUnavailableError as exc:
        logger.warning("checkpointer schema not initialized: %s", exc)
        return SchemaStatus("error", f"checkpointer unavailable: {exc}", exc)
    try:
        async with cm as saver:
            setup = getattr(saver, "setup", None)
            if setup is None:
                logger.info(
                    "checkpointer %s has no setup() — skipping migration",
                    type(saver).__name__,
                )
                return SchemaStatus("skipped", f"{type(saver).__name__} has no setup()")
            await setup()
            logger.info("checkpointer schema ready (%s)", type(saver).__name__)
            return SchemaStatus("ok", f"{type(saver).__name__} schema ready")
    except Exception as exc:
        logger.warning("checkpointer setup failed: %s", exc)
        return SchemaStatus("error", f"setup failed: {exc}", exc)
