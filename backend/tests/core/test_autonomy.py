"""Tests for ``law_ai.core.autonomy`` (spec 018, constitution §12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings

from law_ai.core import autonomy


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


# ---------------------------------------------------------------------------
# BL-20260511-29: --cycle-id idempotency
# ---------------------------------------------------------------------------
def test_reused_cycle_id_replays_instead_of_running_again(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    runs: list[int] = []

    def runner(context: dict) -> dict:
        runs.append(1)
        context["docs"] = 7
        return {"docs_queued": 7}

    first = autonomy.run_cycle("corpus_growth", runner, cycle_id="cid-1")
    second = autonomy.run_cycle("corpus_growth", runner, cycle_id="cid-1")

    assert runs == [1], "the runner must not run twice for one cycle_id"
    assert first["result"] == second["result"] == {"docs_queued": 7}
    assert second["status"] == "ok"
    assert second["cycle_id"] == "cid-1"
    assert second["cycle_type"] == "corpus_growth"
    assert second.get("replayed") is True
    assert first.get("replayed") is None

    types = [e["type"] for e in _events(audit_path)]
    assert types == [
        "autonomy_cycle.start",
        "autonomy_cycle.end",
        "autonomy_cycle.replayed",
    ]


def test_cycle_id_arrives_from_the_payload_too(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI threads --cycle-id through ``payload``, not the kwarg."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    runs: list[int] = []

    def runner(_: dict) -> str:
        runs.append(1)
        return "ok"

    payload = {"kind": "digest", "cycle_id": "cid-payload"}
    autonomy.run_cycle("digest", runner, payload=payload)
    replayed = autonomy.run_cycle("digest", runner, payload=payload)

    assert runs == [1]
    assert replayed["replayed"] is True
    assert replayed["result"] == "ok"


def test_a_fresh_cycle_id_runs_normally(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    runs: list[str] = []

    def runner(_: dict) -> str:
        runs.append("ran")
        return "ok"

    autonomy.run_cycle("test_pillar", runner, cycle_id="cid-a")
    autonomy.run_cycle("test_pillar", runner, cycle_id="cid-b")

    assert runs == ["ran", "ran"]
    assert [e["type"] for e in _events(audit_path)].count("autonomy_cycle.end") == 2


def test_no_cycle_id_never_replays(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two anonymous cycles are two cycles, not one plus a replay."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    runs: list[str] = []

    def runner(_: dict) -> str:
        runs.append("ran")
        return "ok"

    autonomy.run_cycle("test_pillar", runner)
    autonomy.run_cycle("test_pillar", runner)

    assert runs == ["ran", "ran"]
    assert "autonomy_cycle.replayed" not in [e["type"] for e in _events(audit_path)]


def test_kill_switch_wins_over_replay(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deployment switched off after a run stays off for the same id."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    autonomy.run_cycle("test_pillar", lambda _: "ok", cycle_id="cid-switch")

    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", False)
    result = autonomy.run_cycle("test_pillar", lambda _: "ok", cycle_id="cid-switch")

    assert result["status"] == "disabled"
    assert result.get("replayed") is None
    assert _events(audit_path)[-1]["type"] == "autonomy_disabled"


def test_replay_carries_the_prior_error_forward(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed cycle replays as failed — a retry needs a new id."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def boom(_: dict) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        autonomy.run_cycle("test_pillar", boom, cycle_id="cid-err")

    result = autonomy.run_cycle("test_pillar", boom, cycle_id="cid-err")

    assert result["status"] == "error"
    assert result["replayed"] is True
    assert "RuntimeError" in result["error"]


def test_orm_hit_is_preferred_over_the_jsonl_scan(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queryable table wins; JSONL is the no-DB fallback, not the source."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    row = MagicMock()
    row.payload = {
        "type": "autonomy_cycle.end",
        "cycle_id": "cid-orm",
        "cycle_type": "digest",
        "status": "ok",
        "result": {"digest_path": "/var/autonomy/digest-2026-05-11.md"},
    }
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.order_by.return_value = qs
    qs.first.return_value = row

    with patch("law_ai.audit.models.AuditEvent") as model:
        model.objects = qs
        result = autonomy.run_cycle(
            "digest", lambda _: "should-not-run", cycle_id="cid-orm"
        )

    assert result["replayed"] is True
    assert result["result"] == {"digest_path": "/var/autonomy/digest-2026-05-11.md"}
    qs.filter.assert_called_once_with(
        kind="autonomy_cycle.end", payload__cycle_id="cid-orm"
    )


def test_an_unreachable_database_falls_back_to_jsonl(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
    autonomy.run_cycle("digest", lambda _: "first", cycle_id="cid-nodb")

    qs = MagicMock()
    qs.filter.side_effect = RuntimeError("no database configured")
    with patch("law_ai.audit.models.AuditEvent") as model:
        model.objects = qs
        result = autonomy.run_cycle(
            "digest", lambda _: "should-not-run", cycle_id="cid-nodb"
        )

    assert result["replayed"] is True
    assert result["result"] == "first"


# ---------------------------------------------------------------------------
# Progress streaming (BL-20260811-15)
# ---------------------------------------------------------------------------


class _CapturingLayer:
    """A channel layer double recording every group_send."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, dict]] = []

    async def group_send(self, group: str, message: dict) -> None:
        self.sends.append((group, message))


@pytest.fixture()
def ws_capture(monkeypatch: pytest.MonkeyPatch) -> _CapturingLayer:
    from law_ai.agentsapi import streaming

    layer = _CapturingLayer()
    monkeypatch.setattr(streaming, "get_channel_layer", lambda: layer)
    return layer


def test_a_stream_id_publishes_cycle_start_and_end(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def runner(context: dict) -> dict:
        context["digest_path"] = "/var/autonomy/2026-09-05.md"
        return {"ok": True}

    result = autonomy.run_cycle(
        "digest", runner, payload={"kind": "digest"}, stream_id="run-auto.1"
    )

    assert result["status"] == "ok"
    assert {group for group, _ in ws_capture.sends} == {"agent-run-run-auto.1"}
    payloads = [message["payload"] for _group, message in ws_capture.sends]
    assert [p["type"] for p in payloads] == ["autonomy_step", "complete"]
    assert payloads[0]["stage"] == "start"
    # The digest path is the one artefact an operator wants the moment a
    # cycle ends.
    assert payloads[1]["digest_path"] == "/var/autonomy/2026-09-05.md"
    assert payloads[1]["cycle_id"] == result["cycle_id"]


def test_the_stream_id_arrives_from_the_payload_too(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """How --stream-id and the Celery task kwarg reach run_cycle."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    result = autonomy.run_cycle(
        "test_pillar", lambda context: {"ok": True}, payload={"stream_id": "run-kw"}
    )

    assert {group for group, _ in ws_capture.sends} == {"agent-run-run-kw"}
    # The cycle's own audit trail names the socket that watched it.
    assert result["stream_id"] == "run-kw"
    assert _events(audit_path)[-1]["stream_id"] == "run-kw"


def test_a_failing_cycle_still_reports_a_terminal_event(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """Silence must not be the only signal a watched cycle blew up."""
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def runner(context: dict) -> dict:
        raise RuntimeError("ingest exploded")

    with pytest.raises(RuntimeError):
        autonomy.run_cycle("corpus_growth", runner, stream_id="run-boom")

    payloads = [message["payload"] for _group, message in ws_capture.sends]
    assert payloads[-1]["type"] == "complete"
    assert payloads[-1]["status"] == "error"
    assert "ingest exploded" in payloads[-1]["error"]


def test_no_stream_id_emits_nothing(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    autonomy.run_cycle("test_pillar", lambda context: {"ok": True})

    assert ws_capture.sends == []


def test_a_dead_channel_layer_never_fails_a_cycle(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 021 AC-2: streaming is fire-and-forget, not a dependency."""
    from law_ai.agentsapi import streaming

    monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

    def _explode() -> object:
        raise RuntimeError("redis is gone")

    monkeypatch.setattr(streaming, "get_channel_layer", _explode)

    result = autonomy.run_cycle(
        "test_pillar", lambda context: {"ok": True}, stream_id="run-no-redis"
    )

    assert result["status"] == "ok"
