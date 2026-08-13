"""Spike (spec 037 T-002): does OpenInference see `ChatProviderChain`?

The whole of spec 037 rests on one assumption, recorded as the load-bearing
risk in `plan.md` §9: that `openinference-instrumentation-langchain` treats
our *custom* `BaseChatModel` — not a vendor integration, not `ChatAnthropic` —
as an LLM, and so populates `llm.input_messages` / `llm.output_messages`
rather than emitting a contentless `CHAIN` span.

If this file fails, FR-2 cannot be satisfied by instrumenting LangChain and
the fallback is emitting the OpenInference LLM span directly from
`law_ai.core.llm.router` (spec §15 follow-up, promoted into the cycle).

Nothing here calls a real provider: `router.agenerate` is stubbed, exactly as
in `test_llm_langchain.py`. The span exporter is in-memory, so no Phoenix
container is needed either.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from law_ai.core.llm import ChatProviderChain
from law_ai.core.llm.base import LLMResult

# NFR-PERF-1 pins production to BatchSpanProcessor; Simple is a test-only
# choice so assertions can read spans without flushing races.
pytestmark = pytest.mark.unit


@pytest.fixture
def exporter() -> Iterator[InMemorySpanExporter]:
    """Instrument LangChain against a throwaway provider, then undo it."""
    from openinference.instrumentation.langchain import LangChainInstrumentor

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(tracer_provider=provider, skip_dep_check=True)
    try:
        yield memory
    finally:
        # Without this the callback handler leaks into every later test.
        instrumentor.uninstrument()


def _attrs(span: Any) -> dict[str, Any]:
    return dict(span.attributes or {})


def _llm_spans(exporter: InMemorySpanExporter) -> list[Any]:
    return [
        s
        for s in exporter.get_finished_spans()
        if _attrs(s).get("openinference.span.kind") == "LLM"
    ]


async def test_chat_provider_chain_emits_an_llm_span_with_content(
    exporter: InMemorySpanExporter,
) -> None:
    """AC-1's core claim, provable without Phoenix: kind=LLM + real content."""
    model = ChatProviderChain(agent="legal_workflow")
    result = LLMResult(
        text="Marbury established judicial review.",
        provider="claude_code",
        model="claude-opus-5",
        latency_ms=1.0,
    )

    with patch("law_ai.core.llm.router.agenerate", new=AsyncMock(return_value=result)):
        await model.ainvoke("Summarise the holding of Marbury v. Madison")

    llm_spans = _llm_spans(exporter)
    assert llm_spans, (
        "no span with openinference.span.kind=LLM was exported; "
        f"kinds seen: {[_attrs(s).get('openinference.span.kind') for s in exporter.get_finished_spans()]}"
    )

    attrs = _attrs(llm_spans[0])
    # The prompt must be legible — this is the failure the spec's census found
    # (500 spans, zero prompt/completion attributes anywhere).
    input_values = [v for k, v in attrs.items() if k.startswith("llm.input_messages")]
    output_values = [v for k, v in attrs.items() if k.startswith("llm.output_messages")]
    assert input_values, f"llm.input_messages absent; attributes: {sorted(attrs)}"
    assert output_values, f"llm.output_messages absent; attributes: {sorted(attrs)}"
    assert any("Marbury" in str(v) for v in input_values)
    assert any("judicial review" in str(v) for v in output_values)


async def test_llm_span_names_the_model_that_served_the_call(
    exporter: InMemorySpanExporter,
) -> None:
    """Attribution needs the served model, not the configured one (cf. FR-5)."""
    model = ChatProviderChain()
    result = LLMResult(
        text="local answer", provider="ollama", model="mistral", latency_ms=1.0
    )

    with patch("law_ai.core.llm.router.agenerate", new=AsyncMock(return_value=result)):
        await model.ainvoke("q")

    attrs = _attrs(_llm_spans(exporter)[0])
    # ChatProviderChain reports the tier that actually answered in
    # response_metadata; the span must carry it somewhere legible.
    blob = " ".join(str(v) for v in attrs.values())
    assert (
        "mistral" in blob or "ollama" in blob
    ), f"served model absent from span attributes: {sorted(attrs)}"


# ---------------------------------------------------------------------------
# FR-7 / AC-6 / NFR-PRIVACY-1 — content suppression, asserted on exported spans
# ---------------------------------------------------------------------------


async def _run_instrumented(config: Any) -> list[Any]:
    """One ChatProviderChain call under `config`; returns the exported spans."""
    from openinference.instrumentation.langchain import LangChainInstrumentor

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(
        tracer_provider=provider, skip_dep_check=True, config=config
    )
    try:
        result = LLMResult(
            text="Marbury established judicial review.",
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )
        with patch(
            "law_ai.core.llm.router.agenerate", new=AsyncMock(return_value=result)
        ):
            await ChatProviderChain(agent="legal_workflow").ainvoke(
                "Privileged question about ACME Corp"
            )
    finally:
        instrumentor.uninstrument()
    return memory.get_finished_spans()


async def test_content_is_suppressed_but_structure_survives() -> None:
    """AC-6: no prompt or completion text anywhere, span tree intact.

    Asserted over exported attributes rather than by inspection, per
    NFR-PRIVACY-1 — a scrubber that "looked right" but left `input.value`
    populated would pass a code review and fail this.
    """
    from openinference.instrumentation import TraceConfig

    # Baseline with capture ON: the text IS present. Without this the
    # suppression assertion below could pass vacuously (e.g. if the span
    # carried no content in the first place).
    spans = await _run_instrumented(None)
    on_blob = " ".join(str(v) for s in spans for v in dict(s.attributes or {}).values())
    assert "ACME Corp" in on_blob
    assert "judicial review" in on_blob

    spans = await _run_instrumented(TraceConfig(hide_inputs=True, hide_outputs=True))
    attrs = dict(spans[0].attributes or {})
    blob = " ".join(str(v) for v in attrs.values())

    assert "ACME Corp" not in blob, f"prompt text leaked: {sorted(attrs)}"
    assert "judicial review" not in blob, f"completion text leaked: {sorted(attrs)}"
    assert not [k for k in attrs if k.startswith("llm.input_messages")]
    assert not [k for k in attrs if k.startswith("llm.output_messages")]

    # Structure and attribution must survive — that is the whole point of
    # hiding content rather than disabling tracing.
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["llm.model_name"] == "claude-opus-5"
    assert attrs["llm.provider"]


async def test_no_credential_reaches_a_span_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8 / NFR-SEC-1: the OAuth token and API key never become attributes."""
    from django.conf import settings

    sentinel_oauth = "sk-ant-oat01-SENTINEL-OAUTH-TOKEN"
    sentinel_key = "sk-ant-api03-SENTINEL-API-KEY"
    monkeypatch.setattr(settings, "CLAUDE_CODE_OAUTH_TOKEN", sentinel_oauth)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", sentinel_key)

    spans = await _run_instrumented(None)
    for span in spans:
        for key, value in dict(span.attributes or {}).items():
            assert sentinel_oauth not in str(value), f"OAuth token leaked into {key}"
            assert sentinel_key not in str(value), f"API key leaked into {key}"
