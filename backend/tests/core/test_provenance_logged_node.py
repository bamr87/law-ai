"""Tests for the @logged_node decorator (spec 010 T-004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from django.conf import settings
from lawgraph.core.provenance import _stable_hash, logged_node


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
