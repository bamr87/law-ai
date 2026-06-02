"""Tests for ``lawgraph.core.autonomy`` (spec 018, constitution §12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings

from lawgraph.core import autonomy


@pytest.fixture()
def audit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    return target


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_is_enabled_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings default per constitution §12 invariant I3.
    # Monkeypatch in case the env has AUTONOMY_ENABLED=True (e.g. docker-compose).
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", False)
    assert autonomy.is_enabled() is False


def test_run_cycle_short_circuits_when_disabled(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", False)
    called = {"runner": False}

    def runner(context: dict) -> str:
        called["runner"] = True
        return "should-not-run"

    result = autonomy.run_cycle("test_pillar", runner, payload={"a": 1})

    assert called["runner"] is False
    assert result["status"] == "disabled"
    assert result["cycle_type"] == "test_pillar"
    events = _events(audit_path)
    assert len(events) == 1
    assert events[0]["type"] == "autonomy_disabled"
    assert events[0]["cycle_type"] == "test_pillar"
    assert events[0]["details"] == {"a": 1}


def test_run_cycle_emits_paired_start_and_end_events(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def runner(context: dict) -> dict:
        context["items_seen"] = 3
        return {"ok": True}

    result = autonomy.run_cycle(
        "corpus_growth", runner, payload={"frontier": "ca-supreme"}
    )

    assert result["status"] == "ok"
    assert result["result"] == {"ok": True}
    assert result["items_seen"] == 3

    events = _events(audit_path)
    assert [e["type"] for e in events] == [
        "autonomy_cycle.start",
        "autonomy_cycle.end",
    ]
    assert events[0]["cycle_id"] == events[1]["cycle_id"]
    assert events[0]["payload"] == {"frontier": "ca-supreme"}
    assert events[1]["status"] == "ok"
    assert events[1]["items_seen"] == 3
    assert events[1]["duration_ms"] >= 0


def test_run_cycle_records_error_status_on_exception(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def runner(_: dict) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        autonomy.run_cycle("test_pillar", runner)

    events = _events(audit_path)
    end = events[-1]
    assert end["type"] == "autonomy_cycle.end"
    assert end["status"] == "error"
    assert "RuntimeError" in end["error"]


def test_record_policy_violation_writes_event(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    autonomy.record_policy_violation(
        cycle_id="abc-123",
        reason="source_not_allowed",
        payload={"source": "wikipedia"},
    )
    events = _events(audit_path)
    assert len(events) == 1
    assert events[0]["type"] == "policy_violation"
    assert events[0]["cycle_id"] == "abc-123"
    assert events[0]["reason"] == "source_not_allowed"
    assert events[0]["details"] == {"source": "wikipedia"}


def test_is_source_allowed_uses_settings_allow_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "AUTONOMY_ALLOWED_SOURCES", ["courtlistener", "colorado_statutes"]
    )
    assert autonomy.is_source_allowed("courtlistener") is True
    assert autonomy.is_source_allowed("colorado_statutes") is True
    assert autonomy.is_source_allowed("wikipedia") is False
    assert autonomy.allowed_sources() == ("courtlistener", "colorado_statutes")
