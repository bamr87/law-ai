"""The Neo4j driver singleton never crosses event loops (bamr87/bamr87#253).

Fault 4 of the nightly: a driver cached on one test's event loop was reused on
the session loop of ``tests/db/test_backfill_commands_integration.py`` and
failed with ``got Future <Future pending> attached to a different loop``.
These tests need no Neo4j: ``AsyncGraphDatabase.driver`` opens no connection
until a session is used, so driver *identity* per loop is checked directly.
"""

from __future__ import annotations

import asyncio

import pytest

from law_ai.core.neo4j import driver as driver_mod


@pytest.fixture(autouse=True)
def _isolated_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(driver_mod, "_driver", None)
    monkeypatch.setattr(driver_mod, "_driver_loop", None, raising=False)


async def _get() -> object:
    return driver_mod.get_neo4j_driver()


def test_a_second_event_loop_gets_its_own_driver() -> None:
    first = asyncio.run(_get())
    second = asyncio.run(_get())
    assert first is not second


def test_one_event_loop_reuses_one_driver() -> None:
    async def twice() -> tuple[object, object]:
        return driver_mod.get_neo4j_driver(), driver_mod.get_neo4j_driver()

    a, b = asyncio.run(twice())
    assert a is b


def test_a_driver_made_outside_a_loop_is_adopted_by_the_first_loop() -> None:
    outside = driver_mod.get_neo4j_driver()
    inside = asyncio.run(_get())
    assert inside is outside
    assert asyncio.run(_get()) is not outside
