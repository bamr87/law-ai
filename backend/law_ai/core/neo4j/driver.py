"""Async Neo4j driver singleton.

Created lazily so importing this module never touches the network. Tests
that exercise the real driver should use the ``neo4j_driver`` fixture
in ``backend/tests/conftest.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None
#: The event loop ``_driver``'s pooled connections belong to (``None`` until
#: the driver is first used inside a running loop).
_driver_loop: asyncio.AbstractEventLoop | None = None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def get_neo4j_driver() -> AsyncDriver:
    """Return the async Neo4j driver for the running event loop.

    One driver per process *per event loop*. An ``AsyncDriver``'s pooled
    connections are asyncio streams bound to the loop that opened them, so
    handing the same driver to a second loop fails with ``got Future ...
    attached to a different loop`` the moment it reuses a pooled connection
    (bamr87/bamr87#253, fault 4: a driver cached by a function-loop test was
    reused by the session-loop backfill tests). The same happens to any
    process that calls ``asyncio.run`` more than once — a management command
    invoked twice in one worker, for instance. When the loop has changed, the
    stale driver is dropped (its loop is usually closed, so it cannot be
    awaited closed) and a fresh one is created for the current loop.
    """
    global _driver, _driver_loop
    loop = _running_loop()
    stale = (
        _driver is not None
        and loop is not None
        and _driver_loop is not None
        and loop is not _driver_loop
    )
    if stale:
        logger.debug("neo4j: event loop changed; creating a fresh driver")
        _driver = None
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        _driver_loop = loop
    elif _driver_loop is None:
        _driver_loop = loop
    return _driver


async def close_neo4j_driver() -> None:
    """Close the singleton driver (call on ASGI shutdown)."""
    global _driver, _driver_loop
    if _driver is not None:
        await _driver.close()
        _driver = None
        _driver_loop = None


async def run_cypher(
    cypher: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Convenience helper for one-shot reads. Not for hot paths."""
    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(cypher, params or {})
        return [record.data() async for record in result]
