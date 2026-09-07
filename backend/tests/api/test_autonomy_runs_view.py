"""``GET /api/agents/autonomy/runs`` — the cycle log (BL-20260906-23).

``audit.AutonomyRun`` was written on every cycle and read by exactly one
consumer, ``compose_digest``, over a single 24-hour window. "Did the nightly
run, and how did it end" was therefore a question only a container shell could
answer, despite the table carrying a composite ``(kind, -started_at)`` index
put there for precisely this query.

These run against the real table rather than a stubbed manager: the ordering
and the ``?kind=`` filter are the whole point, and a fake manager would assert
the test's own idea of them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/agents/autonomy/runs"


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_API_KEY", None)


def _make_runs() -> None:
    from law_ai.audit.models import AutonomyRun

    base = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)
    rows = [
        ("digest", "ok", 0),
        ("corpus_growth", "ok", 1),
        ("corpus_growth", "error", 2),
        ("test_pillar", "disabled", 3),
    ]
    for kind, status, offset in rows:
        started = base + timedelta(minutes=offset)
        AutonomyRun.objects.create(
            cycle_id=f"cid-{kind}-{offset}",
            kind=kind,
            source="courtlistener" if kind == "corpus_growth" else "",
            trace_id=f"trace-{offset}",
            started_at=started,
            ended_at=started + timedelta(seconds=12),
            status=status,
            duration_ms=12000.0 + offset,
            error="boom" if status == "error" else "",
            summary={"prs_opened": offset},
        )


def _get(**params: Any) -> Any:
    res = APIClient().get(URL, params)
    assert res.status_code == 200, res.content
    return res.json()


def test_returns_every_cycle_newest_first() -> None:
    _make_runs()
    body = _get()
    assert body["available"] is True
    assert body["count"] == 4
    # Newest first: the operator's question is "what just happened".
    assert [r["kind"] for r in body["runs"]] == [
        "test_pillar",
        "corpus_growth",
        "corpus_growth",
        "digest",
    ]
    assert body["by_status"] == {"disabled": 1, "error": 1, "ok": 2}


def test_a_row_carries_kind_status_and_duration() -> None:
    _make_runs()
    row = next(r for r in _get()["runs"] if r["cycle_id"] == "cid-corpus_growth-2")
    assert row["status"] == "error"
    assert row["error"] == "boom"
    assert row["duration_ms"] == pytest.approx(12002.0)
    assert row["source"] == "courtlistener"
    assert row["summary"] == {"prs_opened": 2}
    assert row["started_at"].startswith("2026-09-06T03:02")


def test_kind_filters_on_the_indexed_column() -> None:
    _make_runs()
    body = _get(kind="corpus_growth")
    assert body["kind"] == "corpus_growth"
    assert body["count"] == 2
    assert {r["kind"] for r in body["runs"]} == {"corpus_growth"}


def test_limit_caps_the_page() -> None:
    _make_runs()
    assert _get(limit=1)["count"] == 1


def test_an_out_of_range_limit_is_422() -> None:
    assert APIClient().get(URL, {"limit": "0"}).status_code == 422
    assert APIClient().get(URL, {"limit": "not-a-number"}).status_code == 422


def test_an_empty_table_is_available_and_empty() -> None:
    body = _get()
    assert body["available"] is True
    assert body["runs"] == [] and body["by_status"] == {}


def test_a_database_outage_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same contract as the quarantine panel: no Postgres is not a 500."""
    import law_ai.audit.models as models_mod

    class _Broken:
        @property
        def objects(self) -> Any:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(models_mod, "AutonomyRun", _Broken())
    body = _get()
    assert body["available"] is False
    assert body["runs"] == []


def test_the_panel_is_behind_the_agent_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_API_KEY", "s3cret-test")
    assert APIClient().get(URL).status_code in (401, 403)
    allowed = APIClient().get(URL, **{"HTTP_X_API_KEY": "s3cret-test"})
    assert allowed.status_code == 200
