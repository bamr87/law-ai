"""`logged_node` spans (spec 037 T-006, FR-4, AC-9, NFR-AUDIT-1).

The point of these tests is the *boundary*: the OTEL span is a debugging
surface bolted onto the node, and the constitution-§4 audit write underneath
it must be provably unaffected — written unconditionally, identically, whether
tracing is on or off (spec 037 NG2). A span that swallowed an exception, or an
audit event that only appeared when tracing was live, would both pass a naive
"does it emit a span" test and fail the thing that actually matters.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from law_ai.core.provenance import logged_node

pytestmark = pytest.mark.unit


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    """A real tracer provider scoped to one test.

    `logged_node` resolves its tracer through `trace.get_tracer` at call time,
    so patching the module-global provider getter is enough — no global state
    is mutated and no other test can see it.
    """
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(otel_trace, "get_tracer_provider", lambda: provider)
    yield memory


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every audit event `_record_node_event` persists, in order."""
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "law_ai.core.provenance._persist",
        lambda event: events.append(json.loads(json.dumps(event, default=str))),
    )
    return events


def _attrs(span: Any) -> dict[str, Any]:
    return dict(span.attributes or {})


# ---------------------------------------------------------------------------
# FR-4 — the span itself
# ---------------------------------------------------------------------------


async def test_async_node_emits_chain_span(
    spans: InMemorySpanExporter, captured_events: list[dict[str, Any]]
) -> None:
    @logged_node("draft_answer", model="claude_code/claude-opus-5", prompt_id="irac")
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        return {"answer": "ok"}

    await node({"question": "q"})

    exported = spans.get_finished_spans()
    assert len(exported) == 1
    span = exported[0]
    assert span.name == "node.draft_answer"
    attrs = _attrs(span)
    assert attrs["openinference.span.kind"] == "CHAIN"
    assert attrs["langgraph.node"] == "draft_answer"
    assert attrs["model"] == "claude_code/claude-opus-5"
    assert attrs["prompt_id"] == "irac"
    # Unset metadata must not become a literal "None" attribute.
    assert "prompt_version" not in attrs


def test_sync_node_emits_chain_span(
    spans: InMemorySpanExporter, captured_events: list[dict[str, Any]]
) -> None:
    """The sync and async wrappers are separate closures — both need the span."""

    @logged_node("retrieve")
    def node(state: dict[str, Any]) -> dict[str, Any]:
        return {"passages": []}

    node({"question": "q"})

    exported = spans.get_finished_spans()
    assert len(exported) == 1
    assert exported[0].name == "node.retrieve"
    assert _attrs(exported[0])["openinference.span.kind"] == "CHAIN"


async def test_node_exception_is_recorded_and_reraised(
    spans: InMemorySpanExporter, captured_events: list[dict[str, Any]]
) -> None:
    @logged_node("verify")
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("citation unverifiable")

    with pytest.raises(ValueError, match="citation unverifiable"):
        await node({"question": "q"})

    span = spans.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    assert [e.name for e in span.events] == ["exception"]
    # Pre-existing behavior: a raising node writes no audit event. The span
    # must not have changed that.
    assert captured_events == []


# ---------------------------------------------------------------------------
# AC-9 / NFR-AUDIT-1 — the audit write is not contingent on tracing
# ---------------------------------------------------------------------------


def test_audit_event_written_when_tracing_disabled(
    captured_events: list[dict[str, Any]],
) -> None:
    """No provider patched here: this is the real default-off code path."""

    @logged_node("retrieve", model="ollama/mistral")
    def node(state: dict[str, Any]) -> dict[str, Any]:
        return {"passages": [1, 2]}

    node({"question": "q"})

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event["type"] == "langgraph_node"
    assert event["node"] == "retrieve"
    assert event["model"] == "ollama/mistral"
    assert event["input_hash"] and event["output_hash"]


def test_audit_event_identical_with_and_without_tracing(
    monkeypatch: pytest.MonkeyPatch, captured_events: list[dict[str, Any]]
) -> None:
    """AC-9: byte-identical payloads, modulo the fields that must differ.

    `trace_id` legitimately differs (with tracing on it is the ambient OTEL
    trace, which is the whole point of FR-4) and `latency_ms` is a wall-clock
    measurement. Everything else is the constitution-§4 record and must not
    move.
    """
    volatile = {"trace_id", "latency_ms", "timestamp"}

    @logged_node("draft", model="claude_code/claude-opus-5", prompt_version="v2")
    def node(state: dict[str, Any]) -> dict[str, Any]:
        return {"answer": "same"}

    node({"question": "q"})

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(otel_trace, "get_tracer_provider", lambda: provider)
    node({"question": "q"})

    assert len(captured_events) == 2
    off, on = captured_events
    assert {k: v for k, v in off.items() if k not in volatile} == {
        k: v for k, v in on.items() if k not in volatile
    }
    # And with tracing on, the audit row carries the OTEL trace id, so an
    # auditor can pivot from the audit log straight to the Phoenix trace.
    assert on["trace_id"] == f"{memory.get_finished_spans()[0].context.trace_id:032x}"
