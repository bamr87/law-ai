"""``ENABLE_HUMAN_APPROVAL_GATES`` is a live, audited flag (BL-20260810-03).

The item was filed because the flag was *dead*: nothing read it, so an
operator who set it to False still got quarantine. Spec 029 made it live and
made turning it off leave a trace. Nothing tested that, which meant the
regression could come back silently — stubbing ``_hitl_gates_enabled`` to
``return True`` and deleting the provenance emission left the suite green.

These tests pin all three branches: the gate off commits a sub-threshold
extraction *and* emits ``hitl_gate_disabled``; ``force_quarantine`` still wins
with the gate off (an approval-required source can never be auto-committed);
and the default (armed) gate still quarantines. BL-20260906-92 narrowed the
event to the sub-threshold case — a high-confidence extraction commits with the
gate armed too, so calling that an override over-reported them.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.ingestionapp.services import scout as scout_module
from law_ai.ingestionapp.services.scout import IngestionScout
from tests.ingestion.test_scout import HIGH_CONF_OPINION, LOW_CONF_OPINION


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeDriver:
    def session(self) -> _FakeSession:
        return _FakeSession()


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub the graph writer; returns the case ids it was asked to commit."""
    committed: list[str] = []

    async def fake_commit(session: Any, result: Any) -> int:
        committed.append(result.case_id)
        return 0

    async def noop(*args: Any, **kwargs: Any) -> None:
        return None

    def fake_driver() -> _FakeDriver:
        return _FakeDriver()

    monkeypatch.setattr(scout_module, "get_neo4j_driver", fake_driver)
    monkeypatch.setattr(scout_module, "commit_extraction", fake_commit)
    monkeypatch.setattr(scout_module, "densify_extraction", noop)
    monkeypatch.setattr(scout_module, "densify_statute_extraction", noop)
    return committed


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Capture ``provenance.log_event`` calls made during the run."""
    recorded: list[tuple[str, dict[str, Any]]] = []

    def fake_log_event(event_type: str, payload: dict[str, Any]) -> None:
        recorded.append((event_type, payload))

    monkeypatch.setattr(scout_module.provenance, "log_event", fake_log_event)
    return recorded


@pytest.fixture
def quarantined(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record quarantine routing without touching Celery or the filesystem."""
    routed: list[Any] = []

    async def fake_quarantine(
        self: IngestionScout, result: Any, payload: dict[str, Any]
    ) -> None:
        routed.append(result)

    monkeypatch.setattr(IngestionScout, "_quarantine", fake_quarantine)
    return routed


@pytest.mark.asyncio
async def test_gate_off_commits_a_sub_threshold_extraction(
    settings: Any,
    graph: list[str],
    events: list[tuple[str, dict[str, Any]]],
    quarantined: list[Any],
) -> None:
    """With the gate disarmed, a low-confidence opinion goes to the graph."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = False

    summary = await IngestionScout().run_and_commit(LOW_CONF_OPINION)

    assert summary["committed"] is True
    assert summary["pending"] is False
    assert graph == ["999"], "the flag must reach the commit decision"
    assert quarantined == []


@pytest.mark.asyncio
async def test_gate_off_is_audited(
    settings: Any,
    graph: list[str],
    events: list[tuple[str, dict[str, Any]]],
    quarantined: list[Any],
) -> None:
    """Running without the constitution §5 gate must leave a trace (§4)."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = False

    await IngestionScout().run_and_commit(LOW_CONF_OPINION)

    override = [p for kind, p in events if kind == "hitl_gate_disabled"]
    assert len(override) == 1, "the operator override must be logged exactly once"
    assert override[0]["case_id"] == "999"
    assert override[0]["confidence"] == pytest.approx(
        IngestionScout().extract(LOW_CONF_OPINION).confidence
    )
    assert "ENABLE_HUMAN_APPROVAL_GATES" in override[0]["detail"]
    # BL-20260906-92: the detail names the score and the threshold it missed,
    # instead of asserting "low-confidence" for every document.
    assert "below the 0.70 threshold" in override[0]["detail"]


@pytest.mark.asyncio
async def test_gate_off_does_not_log_an_override_for_high_confidence_work(
    settings: Any,
    graph: list[str],
    events: list[tuple[str, dict[str, Any]]],
    quarantined: list[Any],
) -> None:
    """BL-20260906-92: an extraction that would have committed anyway is not
    an override, and recording it as one inflates the audit trail."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = False

    summary = await IngestionScout().run_and_commit(HIGH_CONF_OPINION)

    assert summary["committed"] is True
    assert graph == ["12345"]
    assert not [kind for kind, _ in events if kind == "hitl_gate_disabled"]


@pytest.mark.asyncio
async def test_force_quarantine_still_wins_with_the_gate_off(
    settings: Any,
    graph: list[str],
    events: list[tuple[str, dict[str, Any]]],
    quarantined: list[Any],
) -> None:
    """A requires_human_approval source is never auto-committed by the flag."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = False

    summary = await IngestionScout().run_and_commit(
        HIGH_CONF_OPINION, force_quarantine=True
    )

    assert summary["committed"] is False
    assert summary["pending"] is True
    assert graph == []
    assert [r.case_id for r in quarantined] == ["12345"]
    assert not [kind for kind, _ in events if kind == "hitl_gate_disabled"]


@pytest.mark.asyncio
async def test_armed_gate_still_quarantines_and_logs_no_override(
    settings: Any,
    graph: list[str],
    events: list[tuple[str, dict[str, Any]]],
    quarantined: list[Any],
) -> None:
    """The default (True) is unchanged: sub-threshold work waits for a human."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = True

    summary = await IngestionScout().run_and_commit(LOW_CONF_OPINION)

    assert summary["committed"] is False
    assert summary["pending"] is True
    assert graph == []
    assert [r.case_id for r in quarantined] == ["999"]
    assert not [kind for kind, _ in events if kind == "hitl_gate_disabled"]


def test_hitl_gates_enabled_reads_the_setting_at_call_time(settings: Any) -> None:
    """Read at call time, not import time, and default to the safe reading."""
    settings.ENABLE_HUMAN_APPROVAL_GATES = False
    assert scout_module._hitl_gates_enabled() is False
    settings.ENABLE_HUMAN_APPROVAL_GATES = True
    assert scout_module._hitl_gates_enabled() is True
