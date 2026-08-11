"""Tests for the @logged_node decorator (spec 010 T-004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from django.conf import settings
from law_ai.core.provenance import _stable_hash, logged_node


@pytest.fixture()
def audit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    return target


def test_stable_hash_is_deterministic_and_short() -> None:
    h1 = _stable_hash({"a": 1, "b": [2, 3]})
    h2 = _stable_hash({"b": [2, 3], "a": 1})
    assert h1 == h2
    assert len(h1) == 16


def test_stable_hash_handles_unserializable_objects() -> None:
    class Weird:
        pass

    # Must not raise.
    h = _stable_hash(Weird())
    assert isinstance(h, str) and h


@pytest.mark.asyncio
async def test_logged_node_records_async_call(audit_path: Path) -> None:
    @logged_node("retrieve", model="mistral:7b", prompt_id="p", prompt_version="1")
    async def node(state: dict) -> dict:
        return {"queries": ["q"], "retrieved": []}

    out = await node({"question": "hi"})
    assert out == {"queries": ["q"], "retrieved": []}

    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "langgraph_node"
    assert event["node"] == "retrieve"
    assert event["model"] == "mistral:7b"
    assert event["prompt_id"] == "p"
    assert event["prompt_version"] == "1"
    assert "input_hash" in event and "output_hash" in event
    assert event["input_hash"] != event["output_hash"]
    assert event["latency_ms"] >= 0


def test_logged_node_records_sync_call(audit_path: Path) -> None:
    @logged_node("cite_check")
    def node(state: dict) -> dict:
        return {"citations": [], "human_approval_required": False}

    out = node({"q": 1})
    assert out["human_approval_required"] is False
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["node"] == "cite_check"


@pytest.mark.asyncio
async def test_logged_node_returns_uuid_when_no_otel(audit_path: Path) -> None:
    """Without an active OTEL span, the trace_id is a UUID4 fallback."""

    @logged_node("retrieve")
    async def node(state: dict) -> dict:
        return {"ok": True}

    await node({})
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    trace_id = events[0]["trace_id"]
    # UUID4 is 36 chars with dashes; OTEL trace ids are 32 hex chars.
    assert len(trace_id) in (32, 36)


@pytest.mark.asyncio
async def test_logged_node_hashes_state_not_self_for_bound_methods(
    audit_path: Path,
) -> None:
    """Bound methods (self, state): input_hash must cover the STATE.

    Regression: the wrapper used ``args[0]`` — the instance — whose repr
    includes a memory address, making every input_hash non-reproducible and
    information-free.
    """

    class Workflow:
        @logged_node("analyze")
        async def analyze(self, state: dict) -> dict:
            return {"answer": "x"}

    state = {"question": "is a clickwrap clause binding?"}
    await Workflow().analyze(state)
    await Workflow().analyze(state)  # different instance, same state

    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(events) == 2
    # Same state ⇒ same reproducible hash, regardless of instance identity.
    assert events[0]["input_hash"] == events[1]["input_hash"]
    assert events[0]["input_hash"] == _stable_hash(state)


def test_log_agent_call_input_hash_is_stable(audit_path: Path) -> None:
    """agent_call input_hash uses _stable_hash, not Python's salted hash()."""
    from law_ai.core.provenance import provenance

    input_data = {"question": "q", "jurisdiction": "US"}
    provenance.log_agent_call("A", input_data, {"ok": 1}, "m", 1.0)
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert events[-1]["input_hash"] == _stable_hash(input_data)


def test_log_event_uses_distinct_type(audit_path: Path) -> None:
    """log_event records the given type — never 'agent_call'."""
    from law_ai.core.provenance import provenance

    provenance.log_event("ws_event_sent", {"analysis_id": "an-1"})
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert events[-1]["type"] == "ws_event_sent"
    assert events[-1]["analysis_id"] == "an-1"
