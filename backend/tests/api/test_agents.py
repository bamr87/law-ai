"""Tests for /api/agents/* (spec 003)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from law_ai.agentsapi import urls as agents_api
from law_ai.core import audit_jsonl as audit_store
from django.conf import settings
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 008: keep the existing tests in default-open mode unless a
    test explicitly opts in to the gate via the ``with_api_key`` fixture."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", None)


@pytest.fixture
def with_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "s3cret-test"
    monkeypatch.setattr(settings, "AGENT_API_KEY", key)
    return key


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_agents_returns_registered(client: AsyncClient) -> None:
    # AC-4 — at least the three agents currently in registry.
    res = await client.get("/api/agents")
    assert res.status_code == 200
    body = res.json()
    names = {a["name"] for a in body["agents"]}
    assert {"LegalAnalyst", "PrecedentHunter", "IngestionScout"}.issubset(names)
    assert body["count"] == len(body["agents"])


@pytest.mark.asyncio
async def test_recent_runs_reads_audit_store(client: AsyncClient) -> None:
    # AC-1 — events recorded earlier surface in /runs newest-first.
    audit_store.record({"agent": "LegalAnalyst", "type": "agent_call", "i": 1})
    audit_store.record({"agent": "PrecedentHunter", "type": "agent_call", "i": 2})
    res = await client.get("/api/agents/runs", params={"limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert body["runs"][0]["i"] == 2  # newest first
    assert body["runs"][1]["i"] == 1


@pytest.mark.asyncio
async def test_recent_runs_validates_limit(client: AsyncClient) -> None:
    res = await client.get("/api/agents/runs", params={"limit": 0})
    assert res.status_code == 422
    res = await client.get("/api/agents/runs", params={"limit": 1000})
    assert res.status_code == 422


def test_parse_backlog_buckets_items() -> None:
    text = """## Open

- **BL-20260101-01** — *feature, high* — Do thing one.
- **BL-20260101-02** — *refactor, low* — Do thing two.

## Claimed

- **BL-20260101-03** — *test-gap, med* — Do thing three. _Surfaced in:_ specs/x.

## Done

- **BL-20251231-01** — *infra, low* — Done thing.
"""
    parsed = agents_api._parse_backlog(text)
    assert parsed["counts"] == {"open": 2, "claimed": 1, "done": 1, "total": 4}
    assert parsed["open"][0]["id"] == "BL-20260101-01"
    assert parsed["open"][0]["kind"] == "feature"
    assert parsed["open"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_backlog_endpoint_against_real_file(client: AsyncClient) -> None:
    # AC-2 — bucketed counts are non-empty and add up to total.
    res = await client.get("/api/agents/backlog")
    assert res.status_code == 200
    body = res.json()
    counts = body["counts"]
    assert counts["total"] == counts["open"] + counts["claimed"] + counts["done"]
    assert counts["total"] >= 1


@pytest.mark.asyncio
async def test_specs_endpoint_lists_known_specs(client: AsyncClient) -> None:
    # AC-3 — both shipped specs appear with parsed status.
    res = await client.get("/api/agents/specs")
    assert res.status_code == 200
    body = res.json()
    ids = {spec["id"] for spec in body["specs"]}
    assert "001-ingest-courtlistener-opinions" in ids
    assert "002-resolve-citations-to-cases" in ids
    for spec in body["specs"]:
        assert spec["status"]  # parsed (may be "planned" / "shipped" / etc.)


def test_provenance_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-5 — log_agent_call must not raise even if persistence blows up.
    from law_ai.core import provenance as prov_mod

    def boom(_event: dict[str, object]) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(prov_mod.audit_store, "record", boom)
    trace_id = prov_mod.provenance.log_agent_call(
        agent_name="X",
        input_data={"a": 1},
        output_data={"b": 2},
        model="ollama/llama3.1",
        latency_ms=1.0,
    )
    assert trace_id  # call still returned a trace id


# --- Spec 008: agent API auth (FR-3, AC-1..AC-4) ---


AGENT_PATHS = [
    "/api/agents",
    "/api/agents/runs",
    "/api/agents/backlog",
    "/api/agents/specs",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", AGENT_PATHS)
async def test_no_key_configured_allows_anonymous(
    client: AsyncClient, path: str
) -> None:
    """AC-1 — when AGENT_API_KEY is unset, no header is required."""
    res = await client.get(path)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_missing_header_when_key_set_returns_401(
    client: AsyncClient, with_api_key: str
) -> None:
    """AC-2 — header missing → 401 missing api key."""
    res = await client.get("/api/agents")
    assert res.status_code == 401
    assert res.json() == {"detail": "missing api key"}


@pytest.mark.asyncio
async def test_wrong_header_when_key_set_returns_401(
    client: AsyncClient, with_api_key: str
) -> None:
    """AC-3 — wrong header → 401 invalid api key."""
    res = await client.get("/api/agents/runs", headers={"X-API-Key": "wrong"})
    assert res.status_code == 401
    assert res.json() == {"detail": "invalid api key"}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", AGENT_PATHS)
async def test_correct_header_when_key_set_passes(
    client: AsyncClient, with_api_key: str, path: str
) -> None:
    """AC-4 — correct header → 200 across every /api/agents/* route."""
    res = await client.get(path, headers={"X-API-Key": with_api_key})
    assert res.status_code == 200


# --- Spec 008 AC-7: startup warning when key unset outside dev ---


def test_startup_warns_when_key_unset_outside_dev(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-7 — emit a single WARNING when AGENT_API_KEY is unset and ENVIRONMENT != development."""
    from law_ai.core import apps as core_apps

    monkeypatch.setattr(settings, "AGENT_API_KEY", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")

    with caplog.at_level("WARNING", logger="law_ai"):
        core_apps.warn_if_unprotected()

    matching = [r for r in caplog.records if "AGENT_API_KEY not set" in r.getMessage()]
    assert len(matching) == 1
