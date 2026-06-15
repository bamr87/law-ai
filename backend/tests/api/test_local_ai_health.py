"""Tests for /api/agents/health/local-ai (spec 010 T-009)."""

from __future__ import annotations

import pytest

# fastapi is an optional test dep (BL-pending: migrate this test to Django's
# async TestClient). Skip the module entirely when fastapi isn't installed so
# CI without the optional dep stays green.
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from lawgraph.agentsapi import urls as agents_api


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from lawgraph.asgi import application as app

    return TestClient(app)


def test_health_endpoint_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_ok() -> dict:
        return {"reachable": True, "detail": "ok"}

    async def _fake_err() -> dict:
        return {"reachable": False, "detail": "no"}

    async def _fake_claude() -> dict:
        return {"provider": "claude_code", "reachable": False, "reason": "off"}

    monkeypatch.setattr(agents_api, "_probe_ollama", _fake_ok)
    monkeypatch.setattr(agents_api, "_probe_checkpointer", _fake_err)
    monkeypatch.setattr(agents_api, "_probe_phoenix", _fake_ok)
    monkeypatch.setattr(agents_api, "_probe_claude_code", _fake_claude)

    resp = client.get("/api/agents/health/local-ai")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"ollama", "checkpointer", "phoenix", "claude_code"}
    assert body["ollama"]["reachable"] is True
    assert body["checkpointer"]["reachable"] is False
    assert body["phoenix"]["reachable"] is True
    assert body["claude_code"]["provider"] == "claude_code"
