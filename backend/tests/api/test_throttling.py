"""Rate limiting on LLM-invoking endpoints (BL-20260810-11).

The gap these close: `/api/analysis` and the LSAT tutor each fan out to a
single local Ollama with a 120 s timeout behind an open-by-default auth
gate, so one client could starve every other user.

Note on technique: the throttle rate is forced by monkeypatching
``ScopedRateThrottle.get_rate`` rather than ``override_settings``. DRF caches
its settings in ``rest_framework.settings.api_settings``, and inside async
tests the restore did not take effect — a 1/min override leaked into every
later test in the session. ``monkeypatch`` is scoped to the test and undone
unconditionally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from django.core.cache import cache
from httpx import ASGITransport, AsyncClient
from rest_framework.throttling import ScopedRateThrottle

from django.conf import settings
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    # DRF keeps throttle history in the cache — clear it so each test starts
    # from an empty bucket regardless of execution order.
    cache.clear()
    yield
    cache.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _force_rate(monkeypatch: pytest.MonkeyPatch, rate: str) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "get_rate", lambda self: rate)


_BODY = {"text": "Contract dispute.", "use_langgraph": False}


@pytest.mark.asyncio
async def test_analysis_is_throttled_after_the_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_rate(monkeypatch, "1/min")
    first = await client.post("/api/analysis", json=_BODY)
    second = await client.post("/api/analysis", json=_BODY)
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_analysis_not_throttled_under_the_limit(client: AsyncClient) -> None:
    """The suite's configured rate must not trip on ordinary use."""
    for _ in range(3):
        res = await client.post("/api/analysis", json=_BODY)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_cheap_read_endpoints_are_not_throttled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only LLM-invoking endpoints carry the `llm` scope."""
    _force_rate(monkeypatch, "1/min")
    for _ in range(5):
        res = await client.get("/api/lsat/sections")
        assert res.status_code == 200


def test_llm_scope_is_applied_to_the_right_views() -> None:
    from law_ai.analysis.urls import AnalysisView
    from law_ai.lsat.urls import GradeView, TutorView

    assert AnalysisView.throttle_scope == "llm"
    assert TutorView.throttle_scope == "llm"
    # Grading is deterministic (no model call) — must stay unthrottled.
    assert getattr(GradeView, "throttle_scope", None) is None


def test_production_default_rate_is_configured() -> None:
    """base.py ships a real limit even though the suite raises it."""
    from law_ai.settings import base

    assert base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["llm"] == "20/min"
