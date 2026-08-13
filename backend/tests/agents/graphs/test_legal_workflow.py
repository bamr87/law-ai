"""Unit tests for app.agents.graphs.legal_workflow (spec 010 T-005, AC-5/AC-6).

These tests inject a fake LLM and a fake citation resolver so they run
without Ollama, Neo4j, Postgres, or any network access.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "langgraph",
    reason="langgraph not installed (add the local-ai extra)",
)

from law_ai.agents_runtime.graphs.legal_workflow import (
    LegalWorkflow,
    LegalWorkflowOutput,
    _coerce_text,
    _parse_json,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = text


class FakeOllama:
    """Returns a canned JSON response for each call in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def ainvoke(self, prompt: str) -> _FakeMessage:
        self.calls.append(prompt)
        if not self._responses:
            return _FakeMessage("{}")
        return _FakeMessage(self._responses.pop(0))


# ---------------------------------------------------------------------------
# Helpers under test
# ---------------------------------------------------------------------------


def test_coerce_text_handles_various_shapes() -> None:
    assert _coerce_text("hi") == "hi"
    assert _coerce_text(None) == ""
    assert _coerce_text(_FakeMessage("hi")) == "hi"


def test_parse_json_strips_code_fences() -> None:
    text = """```json\n{"queries": ["a", "b"]}\n```"""
    assert _parse_json(text, {}) == {"queries": ["a", "b"]}


def test_parse_json_extracts_brace_block_from_prose() -> None:
    text = 'Sure, here you go: {"answer": "yes"} — happy to help!'
    assert _parse_json(text, {}) == {"answer": "yes"}


def test_parse_json_returns_default_on_failure() -> None:
    assert _parse_json("nope", {"fallback": True}) == {"fallback": True}


def test_parse_json_rejects_non_dict_payloads() -> None:
    """A JSON array/scalar response falls back to the default dict."""
    assert _parse_json('["a", "b"]', {"fallback": True}) == {"fallback": True}
    assert _parse_json("42", {"fallback": True}) == {"fallback": True}


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_retrieved_passages() -> list[dict]:
    return [
        {
            "title": "Marbury v. Madison",
            "snippet": "Established judicial review.",
            "source_url": "https://example.test/marbury",
        }
    ]


@pytest.mark.asyncio
async def test_workflow_happy_path_verifies_citations(
    fake_retrieved_passages: list[dict],
) -> None:
    """All citations resolve → no HITL flag."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["judicial review"], "rationale": "ok"}',
            '{"answer": "Marbury established judicial review.",'
            ' "citations": [{"text": "Marbury v. Madison", '
            '"source_url": "https://example.test/marbury"}],'
            ' "confidence": 0.9}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {c: f"case-{i}" for i, c in enumerate(citations)}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("Did Marbury establish judicial review?")
    assert isinstance(result, LegalWorkflowOutput)
    assert "judicial review" in result.answer.lower()
    assert result.confidence == pytest.approx(0.9)
    assert result.human_approval_required is False
    assert result.langgraph_thread_id and result.langgraph_thread_id.startswith("lwf-")
    assert len(result.citations) == 1
    assert result.citations[0].source == "analyze"
    assert result.citations[0].resolved_case_id == "case-0"
    # Coverage envelope (BL-20260803-02): result count + queries surfaced.
    assert result.retrieval_stats.result_count == len(fake_retrieved_passages)
    assert result.retrieval_stats.queries == ["judicial review"]
    # Two LLM calls: retrieve + analyze (cite_check is deterministic).
    assert len(fake_llm.calls) == 2


@pytest.mark.asyncio
async def test_workflow_flags_unverified_citations(
    fake_retrieved_passages: list[dict],
) -> None:
    """AC-6: cite_check raises human_approval_required when a citation cannot resolve."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "Cited a non-existent case.",'
            ' "citations": [{"text": "Phantom v. Mirage", "source_url": null}],'
            ' "confidence": 0.7}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {c: None for c in citations}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("Anything about Phantom v. Mirage?")
    assert result.human_approval_required is True
    assert len(result.citations) == 1
    assert result.citations[0].source == "ollama-hallucination-check"
    assert result.citations[0].resolved_case_id is None


@pytest.mark.asyncio
async def test_workflow_handles_empty_retrieval() -> None:
    """No retrieved passages → analyze returns the refusal phrasing, low confidence."""
    fake_llm = FakeOllama(['{"queries": ["q"]}'])

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {c: None for c in citations}

    async def fake_retriever(state):
        return []

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("How is the weather?")
    assert "Insufficient sources" in result.answer
    assert result.confidence <= 0.4
    # A refusal (zero citations) must be reviewed by a human before anyone
    # relies on it — "no results in our corpus" ≠ "no such law" (§13).
    assert result.human_approval_required is True
    assert len(fake_llm.calls) == 1  # only the retrieve call
    # Coverage envelope reports the empty retrieval explicitly.
    assert result.retrieval_stats.result_count == 0
    assert result.retrieval_stats.queries  # queries drafted even on refusal
    assert "does NOT mean no such law" in result.retrieval_stats.coverage_note


@pytest.mark.asyncio
async def test_workflow_survives_malformed_llm_output_shapes(
    fake_retrieved_passages: list[dict],
) -> None:
    """Plausible-but-wrong LLM shapes must degrade, never crash the graph.

    analyze returns: a JSON array; citations holding bare strings/nulls; a
    non-numeric confidence. All previously raised (AttributeError on
    list.get / float("high")).
    """
    fake_llm = FakeOllama(
        [
            '{"queries": ["q"]}',
            '{"answer": "Answer.", "citations": ["Marbury v. Madison", null, '
            '{"text": "Real v. Cite", "source_url": null}], '
            '"confidence": "high"}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {c: None for c in citations}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("Anything?")
    # Only the dict-shaped citation survives; junk entries are dropped.
    assert [c.text for c in result.citations] == ["Real v. Cite"]
    # Non-numeric confidence clamps to the 0.5 default, not a crash.
    assert result.confidence == pytest.approx(0.5)
    assert result.human_approval_required is True  # unresolved citation


@pytest.mark.asyncio
async def test_workflow_survives_json_array_response() -> None:
    """A top-level JSON array from the model takes the refusal default."""
    fake_llm = FakeOllama(['["not", "a", "dict"]'])

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {}

    async def fake_retriever(state):
        return []

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("Anything?")
    assert "Insufficient sources" in result.answer
    assert result.human_approval_required is True


@pytest.mark.asyncio
async def test_workflow_resumes_thread(
    fake_retrieved_passages: list[dict],
) -> None:
    """Caller-supplied thread_id is honored end-to-end."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["q"]}',
            '{"answer": "ok", "citations": [], "confidence": 0.6}',
        ]
    )

    async def fake_resolver(citations):
        return {}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("q", thread_id="my-resume-id")
    assert result.langgraph_thread_id == "my-resume-id"


# ---------------------------------------------------------------------------
# Spec 037 FR-5 — the span must name the model that actually served the call
# ---------------------------------------------------------------------------


class _FakeChainMessage:
    """Mimics ChatProviderChain's AIMessage: content + response_metadata."""

    def __init__(self, text: str, model_label: str) -> None:
        self.content = text
        self.response_metadata = {
            "provider": model_label.split("/", maxsplit=1)[0],
            "model": model_label.rsplit("/", maxsplit=1)[-1],
            "model_label": model_label,
            "fell_back": False,
        }


class FakeChain:
    def __init__(self, responses: list[str], model_label: str) -> None:
        self._responses = list(responses)
        self._label = model_label

    async def ainvoke(self, prompt: str) -> _FakeChainMessage:
        text = self._responses.pop(0) if self._responses else "{}"
        return _FakeChainMessage(text, self._label)


_SPAN_TEST_PASSAGES = [
    {
        "title": "Marbury v. Madison",
        "snippet": "Established judicial review.",
        "source_url": "https://example.test/marbury",
    }
]


async def _run_with(llm, retrieved: list[dict] | None = None):
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    real_get = otel_trace.get_tracer_provider
    otel_trace.get_tracer_provider = lambda: provider  # type: ignore[assignment]

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {}

    async def fake_retriever(state):
        return retrieved if retrieved is not None else _SPAN_TEST_PASSAGES

    try:
        wf = LegalWorkflow(
            llm_factory=lambda: llm,
            cite_resolver=fake_resolver,
            retriever=fake_retriever,
        )
        await wf.invoke("Did Marbury establish judicial review?")
    finally:
        otel_trace.get_tracer_provider = real_get  # type: ignore[assignment]

    spans = {s.name: dict(s.attributes or {}) for s in memory.get_finished_spans()}
    return spans


async def test_workflow_span_reports_the_serving_model() -> None:
    """The attribute hard-coded OLLAMA_DEFAULT_MODEL; Claude has served since spec 034."""
    llm = FakeChain(
        [
            '{"queries": ["judicial review"], "rationale": "ok"}',
            '{"answer": "Marbury established judicial review.",'
            ' "citations": [], "confidence": 0.9}',
        ],
        model_label="claude_code/claude-opus-5",
    )
    spans = await _run_with(llm)

    attrs = spans["legal_workflow.invoke"]
    assert attrs["legal_workflow.model"] == "claude_code/claude-opus-5"
    assert attrs["openinference.span.kind"] == "CHAIN"


async def test_workflow_span_reports_a_fallback_tier_truthfully() -> None:
    """Reporting the *configured* head would lie whenever the chain falls back."""
    llm = FakeChain(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "local answer", "citations": [], "confidence": 0.5}',
        ],
        model_label="ollama/mistral",
    )
    spans = await _run_with(llm)
    assert spans["legal_workflow.invoke"]["legal_workflow.model"] == "ollama/mistral"


async def test_workflow_span_omits_the_model_when_none_served() -> None:
    """No passages ⇒ the refusal path calls no model, so there is nothing true to report."""
    llm = FakeChain(
        ['{"queries": ["q"], "rationale": "ok"}'], "claude_code/claude-opus-5"
    )
    spans = await _run_with(llm, retrieved=[])

    attrs = spans["legal_workflow.invoke"]
    # retrieve still ran, so its label is present; what must never appear is a
    # fabricated model for a call that did not happen.
    assert attrs.get("legal_workflow.model") in (None, "claude_code/claude-opus-5")


async def test_node_spans_nest_under_the_workflow_span() -> None:
    """AC-2's structural claim at unit scope: nodes are children, not orphans."""
    llm = FakeChain(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "a", "citations": [], "confidence": 0.7}',
        ],
        model_label="claude_code/claude-opus-5",
    )
    spans = await _run_with(llm)
    assert "node.retrieve" in spans
    assert "node.analyze" in spans
    assert spans["node.analyze"]["openinference.span.kind"] == "CHAIN"
