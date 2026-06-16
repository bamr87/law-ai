"""Tests for the WS3/WS4 agent endpoints: /api/agents/{autonomy,sessions}."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_sessions_list_and_detail(client) -> None:
    from lawgraph.audit import session_ledger
    from lawgraph.core.provenance import provenance, session_scope

    session_ledger.start_session("api-sess", agent_source="claude_code", kind="evolve")
    with session_scope("api-sess"):
        provenance.log_agent_call("A", {}, {"r": 1}, "m", 2.0)
    session_ledger.finalize_session("api-sess", status="completed", summary="ok")

    res = client.get("/api/agents/sessions")
    assert res.status_code == 200
    body = res.json()
    assert any(s["session_id"] == "api-sess" for s in body["sessions"])

    detail = client.get("/api/agents/sessions/api-sess")
    assert detail.status_code == 200
    d = detail.json()
    assert d["session"]["status"] == "completed"
    assert d["session"]["agent_source"] == "claude_code"
    assert d["count"] >= 1  # the logged agent_call event is linked by session_id


@pytest.mark.django_db
def test_sessions_filter_by_status(client) -> None:
    from lawgraph.audit import session_ledger

    session_ledger.start_session("run-1", kind="evolve")  # status running
    session_ledger.finalize_session("done-1", status="completed")

    res = client.get("/api/agents/sessions", {"status": "running"})
    assert res.status_code == 200
    ids = {s["session_id"] for s in res.json()["sessions"]}
    assert "run-1" in ids and "done-1" not in ids


@pytest.mark.django_db
def test_autonomy_endpoint(client, settings) -> None:
    settings.AUTONOMY_ENABLED = True
    from lawgraph.core.autonomy import run_cycle

    run_cycle("evolve", lambda c: {"ok": 1})

    res = client.get("/api/agents/autonomy")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert body["last_cycle"] is not None
    assert body["last_cycle"]["cycle_type"] == "evolve"
    assert body["last_cycle"]["status"] == "ok"


@pytest.mark.django_db
def test_autonomy_endpoint_disabled_default(client) -> None:
    res = client.get("/api/agents/autonomy")
    assert res.status_code == 200
    assert res.json()["enabled"] is False
