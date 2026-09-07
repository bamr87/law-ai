"""TopicFrontier dispatch really fetches under a running loop (BL-20260511-08).

The bug this pins: ``_dispatch_target`` is async, adapters' sync ``fetch``
called ``asyncio.run`` internally, and a nested ``asyncio.run`` inside the
autonomy loop raises ``RuntimeError`` — swallowed by the dispatch node's bare
``except`` and logged as "fetch failed". Every real ``corpus_growth`` run
therefore fetched nothing, and no test caught it because every test mocked
``adapter.fetch``.

So this module uses a **real** adapter (with only the HTTP layer faked by
respx) driven through the real dispatch coroutine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from law_ai.agents_runtime.graphs.topic_frontier import (
    _adapter_docs,
    _dispatch_target,
)
from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter

FIXTURE = (
    Path(__file__).parent / "fixtures" / "co" / "title_18_article_3.html"
).read_text(encoding="utf-8")


@pytest.mark.asyncio
@respx.mock
async def test_real_adapter_is_dispatched_from_inside_the_event_loop() -> None:
    respx.get(url__regex=r".*/title-18/").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    scout = MagicMock()
    scout.run_and_commit = AsyncMock(
        return_value={"committed": True, "confidence": 0.9, "edges": 1}
    )

    dispatched: list[dict[str, Any]] = []
    result = await _dispatch_target(scout, ColoradoStatutesAdapter(), "18", dispatched)

    assert result, (
        "dispatch fetched nothing from a real adapter — the nested "
        "asyncio.run regression is back (BL-20260511-08)"
    )
    assert all(d["source_name"] == "colorado_statutes" for d in result)
    assert scout.run_and_commit.await_count == len(result)


@pytest.mark.asyncio
@respx.mock
async def test_force_quarantine_flag_survives_the_afetch_switch() -> None:
    """Now that dispatch really fetches, the HITL flag must still be honoured."""
    respx.get(url__regex=r".*/title-18/").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    scout = MagicMock()
    scout.run_and_commit = AsyncMock(
        return_value={"committed": False, "confidence": 0.9, "edges": 0}
    )

    await _dispatch_target(
        scout,
        ColoradoStatutesAdapter(),
        "18",
        [],
        force_quarantine=True,
    )
    assert scout.run_and_commit.await_count >= 1
    for call in scout.run_and_commit.await_args_list:
        assert call.kwargs["force_quarantine"] is True


@pytest.mark.asyncio
async def test_duck_typed_sync_adapter_still_works() -> None:
    """A third-party adapter with only ``fetch`` runs in a worker thread."""

    class _SyncOnly:
        name = "legacy"

        def fetch(self, query: str, *, limit: int = 10) -> list[Any]:
            doc = MagicMock()
            doc.source_name = "legacy"
            doc.source_url = f"https://legacy.test/{query}"
            doc.title = query
            doc.text = "body"
            return [doc]

    docs = await _adapter_docs(_SyncOnly(), "q", limit=5)
    assert [d.title for d in docs] == ["q"]


@pytest.mark.asyncio
async def test_afetch_is_preferred_over_fetch_when_both_exist() -> None:
    class _Both:
        name = "both"

        def fetch(self, query: str, *, limit: int = 10) -> list[Any]:
            raise AssertionError("sync fetch must not be used inside the loop")

        async def afetch(self, query: str, *, limit: int = 10) -> list[Any]:
            doc = MagicMock()
            doc.title = query
            return [doc]

    docs = await _adapter_docs(_Both(), "async-path", limit=3)
    assert [d.title for d in docs] == ["async-path"]
