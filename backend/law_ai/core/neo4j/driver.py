"""Async Neo4j driver singleton.

Created lazily so importing this module never touches the network. Tests
that exercise the real driver should use the ``neo4j_driver`` fixture
in ``backend/tests/conftest.py``.
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from law_ai.core.settings_proxy import settings_proxy as settings

_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    """Return a process-wide async Neo4j driver, creating it on first use."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """Close the singleton driver (call on ASGI shutdown)."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def run_cypher(
    cypher: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Convenience helper for one-shot reads. Not for hot paths."""
    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(cypher, params or {})
        return [record.data() async for record in result]
