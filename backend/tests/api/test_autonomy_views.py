"""Tests for /api/agents/autonomy/* (BL-20260511-03).

The three panels behind the read-only autonomy dashboard. The recurring
theme is *absence is reported, never crashed*: `history.jsonl`, `coverage.xml`
and Postgres are all things a fresh checkout legitimately lacks, and a
dashboard that 500s in that state is worse than one that says "no data yet".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from django.conf import settings
from httpx import ASGITransport, AsyncClient

from law_ai.asgi import application as app

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_API_KEY", None)


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _write_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list) -> Path:
    from law_ai.agentsapi import autonomy_views

    target = tmp_path / "history.jsonl"
    target.write_text(
        "".join(json.dumps(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    monkeypatch.setattr("law_ai.eval.paths.HISTORY_PATH", target, raising=True)
    assert autonomy_views.HISTORY_MAX >= 1
    return target


# ---------------------------------------------------------------------------
# LegalBench history
# ---------------------------------------------------------------------------
async def test_history_reports_absence_instead_of_failing(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "law_ai.eval.paths.HISTORY_PATH", tmp_path / "nope.jsonl", raising=True
    )
    res = await client.get("/api/agents/autonomy/legalbench-history")

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["runs"] == []
    assert body["series"] == []
    assert body["count"] == 0


async def test_history_pivots_runs_into_one_series_per_subset(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_history(
        tmp_path,
        monkeypatch,
        [
            {
                "run_id": "r1",
                "timestamp": "2026-05-01T00:00:00Z",
                "model": "mistral",
                "accuracies": {"abercrombie": 0.50, "canada_tax_court": 0.60},
            },
            {
                "run_id": "r2",
                "timestamp": "2026-05-02T00:00:00Z",
                "model": "mistral",
                "accuracies": {"abercrombie": 0.62},
            },
        ],
    )

    res = await client.get("/api/agents/autonomy/legalbench-history")
    body = res.json()

    assert body["available"] is True
    assert body["count"] == 2
    series = {s["subset"]: s for s in body["series"]}
    assert set(series) == {"abercrombie", "canada_tax_court"}
    # Aligned x-axis: a subset not measured in a run contributes None.
    assert series["abercrombie"]["points"] == [0.50, 0.62]
    assert series["canada_tax_court"]["points"] == [0.60, None]
    assert series["abercrombie"]["delta_pp"] == 12.0
    assert series["abercrombie"]["latest"] == 0.62
    # One measurement is not a trend.
    assert series["canada_tax_court"]["delta_pp"] is None


async def test_history_is_oldest_first_and_limited(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sparkline reads left to right; reversing in the browser is a bug."""
    _write_history(
        tmp_path,
        monkeypatch,
        [
            {"run_id": f"r{i}", "accuracies": {"abercrombie": i / 10}}
            for i in range(1, 6)
        ],
    )

    res = await client.get(
        "/api/agents/autonomy/legalbench-history", params={"limit": 3}
    )
    body = res.json()

    assert [r["run_id"] for r in body["runs"]] == ["r3", "r4", "r5"]
    assert body["series"][0]["points"] == [0.3, 0.4, 0.5]


async def test_history_survives_a_truncated_line(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "history.jsonl"
    target.write_text(
        json.dumps({"run_id": "good", "accuracies": {"abercrombie": 0.7}})
        + '\n{"run_id": "trunc\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("law_ai.eval.paths.HISTORY_PATH", target, raising=True)

    res = await client.get("/api/agents/autonomy/legalbench-history")
    body = res.json()

    assert body["available"] is True
    assert [r["run_id"] for r in body["runs"]] == ["good"]


async def test_history_rejects_an_out_of_range_limit(client: AsyncClient) -> None:
    res = await client.get(
        "/api/agents/autonomy/legalbench-history", params={"limit": 0}
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Recent quarantine
# ---------------------------------------------------------------------------
async def test_quarantine_reports_absence_when_the_db_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Postgres is a normal dev state, not a dashboard outage."""

    class _Broken:
        @property
        def objects(self) -> Any:
            raise RuntimeError("connection refused")

    import law_ai.ingestionapp.models as models_mod

    monkeypatch.setattr(models_mod, "PendingReview", _Broken())
    res = await client.get("/api/agents/autonomy/recent-quarantine")

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["documents"] == []


async def test_quarantine_returns_the_ten_newest(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    import law_ai.ingestionapp.models as models_mod

    class _Row:
        def __init__(self, i: int) -> None:
            self.id = f"doc-{i}"
            self.source = "courtlistener"
            self.kind = "case"
            self.confidence = 0.4 + i / 100
            self.reason = "low confidence"
            self.created_at = datetime(2026, 5, 11, 12, i, tzinfo=UTC)
            self.reviewed_at = None
            self.approved = None

    rows = [_Row(i) for i in range(20)]

    class _Manager:
        def order_by(self, field: str) -> list[_Row]:
            assert field == "-created_at"
            return rows

    class _Model:
        objects = _Manager()

    monkeypatch.setattr(models_mod, "PendingReview", _Model)
    res = await client.get("/api/agents/autonomy/recent-quarantine")
    body = res.json()

    assert body["available"] is True
    assert body["count"] == 10
    assert body["documents"][0]["id"] == "doc-0"
    assert body["documents"][0]["kind"] == "case"
    assert body["documents"][0]["reviewed"] is False
    assert body["documents"][0]["created_at"].startswith("2026-05-11T12:00")


# ---------------------------------------------------------------------------
# Auth parity with the rest of /api/agents/*
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/agents/autonomy/legalbench-history",
        "/api/agents/autonomy/recent-quarantine",
        "/api/agents/autonomy/runs",
    ],
)
async def test_panels_are_behind_the_agent_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    monkeypatch.setattr(settings, "AGENT_API_KEY", "s3cret-test")

    denied = await client.get(endpoint)
    assert denied.status_code in (401, 403)

    allowed = await client.get(endpoint, headers={"X-API-Key": "s3cret-test"})
    assert allowed.status_code == 200
