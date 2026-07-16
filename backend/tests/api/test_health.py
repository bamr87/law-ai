"""Unit tests for /health (specs/001 AC-4)."""

from __future__ import annotations

from datetime import datetime, UTC

import pytest
from httpx import ASGITransport, AsyncClient

from law_ai.core import urls_health as health_module
from law_ai.asgi import application as app


@pytest.mark.asyncio
async def test_health_returns_null_when_no_ingest(monkeypatch) -> None:
    async def fake_driver():  # pragma: no cover — replaced
        ...

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _FakeDriver:
        def session(self):
            return _FakeSession()

    monkeypatch.setattr(health_module, "get_neo4j_driver", _FakeDriver)

    async def _none(_session):
        return None

    monkeypatch.setattr(health_module, "get_last_ingest_at", _none)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["last_ingest_at"] is None


@pytest.mark.asyncio
async def test_health_returns_iso_timestamp_when_present(monkeypatch) -> None:
    stamp = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _FakeDriver:
        def session(self):
            return _FakeSession()

    monkeypatch.setattr(health_module, "get_neo4j_driver", _FakeDriver)

    async def _ts(_session):
        return stamp

    monkeypatch.setattr(health_module, "get_last_ingest_at", _ts)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["last_ingest_at"] == stamp.isoformat()


@pytest.mark.asyncio
async def test_health_never_raises_on_db_error(monkeypatch) -> None:
    def boom():
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(health_module, "get_neo4j_driver", boom)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["last_ingest_at"] is None
