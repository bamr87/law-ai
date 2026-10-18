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
    # court + decided_at are on every real GraphRAG passage and are what
    # cite_check backfills each citation's §13 attribution from
    # (BL-20260803-04); a fixture without them would exercise the
    # under-attributed path, which test_attribution_rule.py covers on purpose.
    return [
        {
            "title": "Marbury v. Madison",
            "snippet": "Established judicial review.",
            "source_url": "https://example.test/marbury",
            "court": "us-supreme",
            "decided_at": "1803-02-24",
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
# BL-20260803-02: the coverage envelope reaches the model and the caller
# ---------------------------------------------------------------------------


class _CoverageRetriever:
    """Retriever that publishes a real RetrievalCoverage, like GraphRAG does."""

    def __init__(self, passages, coverage):  # type: ignore[no-untyped-def]
        self._passages = passages
        self.last_coverage = coverage

    async def __call__(self, state):  # type: ignore[no-untyped-def]
        return list(self._passages)


def _coverage(**kwargs):  # type: ignore[no-untyped-def]
    from law_ai.agents_runtime.tools.graph_rag import RetrievalCoverage

    return RetrievalCoverage(**kwargs)


@pytest.mark.asyncio
async def test_analyze_prompt_relays_the_coverage_note_verbatim() -> None:
    """The note must reach the model, not just the UI sidecar."""
    coverage = _coverage(
        queries=["judicial review"],
        result_count=1,
        lexical_count=1,
        jurisdictions_present=["us-supreme"],
        jurisdiction_requested="us-ca",
        jurisdiction_absent=True,
        date_earliest="1803-02-24",
        date_latest="1803-02-24",
    )
    passages = [
        {
            "title": "Marbury v. Madison",
            "snippet": "Established judicial review.",
            "source_url": "https://example.test/marbury",
            "court": "us-supreme",
            "decided_at": "1803-02-24",
        }
    ]
    fake_llm = FakeOllama(
        [
            '{"queries": ["judicial review"], "rationale": "ok"}',
            '{"answer": "…", "citations": [], "confidence": 0.5}',
        ]
    )

    async def resolver(citations):  # type: ignore[no-untyped-def]
        return {}

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=resolver,
        retriever=_CoverageRetriever(passages, coverage),
    )
    result = await wf.invoke(
        "Did Marbury establish judicial review?", jurisdiction="us-ca"
    )

    analyze_prompt = fake_llm.calls[1]
    assert "CORPUS COVERAGE (restate this verbatim" in analyze_prompt
    assert coverage.note() in analyze_prompt
    # …and the same note travels to the caller unchanged.
    assert result.retrieval_stats.coverage_note == coverage.note()
    assert result.retrieval_stats.date_earliest == "1803-02-24"
    assert result.retrieval_stats.date_latest == "1803-02-24"
    assert result.retrieval_stats.jurisdictions_present == ["us-supreme"]
    assert result.retrieval_stats.jurisdiction_absent is True


@pytest.mark.asyncio
async def test_no_coverage_note_means_no_preamble() -> None:
    """A retriever without coverage must not inject an empty coverage block."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "…", "citations": [], "confidence": 0.5}',
        ]
    )

    async def resolver(citations):  # type: ignore[no-untyped-def]
        return {}

    async def retriever(state):  # type: ignore[no-untyped-def]
        return [{"title": "T", "snippet": "s", "source_url": "u"}]

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm, cite_resolver=resolver, retriever=retriever
    )
    await wf.invoke("q?")
    assert "CORPUS COVERAGE" not in fake_llm.calls[1]


@pytest.mark.asyncio
async def test_model_label_records_the_serving_provider() -> None:
    """BL-20260615-02: provenance names the tier that answered, not Ollama."""

    class _LabelledMessage:
        def __init__(self, text: str) -> None:
            self.content = text
            self.response_metadata = {
                "provider": "claude_code",
                "model": "claude-opus-5-5",
                "model_label": "claude_code/claude-opus-5",
            }

    class _LabelledLLM:
        def __init__(self, responses):  # type: ignore[no-untyped-def]
            self._responses = list(responses)

        async def ainvoke(self, prompt: str):  # type: ignore[no-untyped-def]
            return _LabelledMessage(self._responses.pop(0))

    from law_ai.agents_runtime.graphs.legal_workflow import _coerce_model_label

    assert _coerce_model_label("bare string") == "(provider chain)"
    assert _coerce_model_label(_LabelledMessage("{}")) == "claude_code/claude-opus-5"

    async def resolver(citations):  # type: ignore[no-untyped-def]
        return {}

    async def retriever(state):  # type: ignore[no-untyped-def]
        return [{"title": "T", "snippet": "s", "source_url": "u"}]

    labelled = _LabelledLLM(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "a", "citations": [], "confidence": 0.5}',
        ]
    )
    wf = LegalWorkflow(
        llm_factory=lambda: labelled,
        cite_resolver=resolver,
        retriever=retriever,
    )
    # Smoke: the run completes with the labelled message shape.
    out = await wf.invoke("q?")
    assert out.answer == "a"


# ---------------------------------------------------------------------------
# The IRAC split the analyze node now returns (BL-20260511-06)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_returns_the_irac_split(
    fake_retrieved_passages: list[dict],
) -> None:
    """LegalAnalyst's backfill: issue/rule/conclusion come off the workflow."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["judicial review"], "rationale": "ok"}',
            '{"issue": "Whether the Court may void an act of Congress.",'
            ' "rule": "A law repugnant to the Constitution is void '
            '(Marbury v. Madison, U.S. Supreme Court, 1803).",'
            ' "answer": "Applying that rule to these facts…",'
            ' "conclusion": "The provision is unenforceable.",'
            ' "citations": [{"text": "Marbury v. Madison",'
            ' "source_url": "https://example.test/marbury"}],'
            ' "confidence": 0.9}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {c: "case-0" for c in citations}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("May the Court void an act of Congress?")

    assert result.issue.startswith("Whether the Court may void")
    assert "repugnant to the Constitution" in result.rule
    assert result.conclusion == "The provision is unenforceable."
    assert result.answer.startswith("Applying that rule")
    # The prompt has to ask for them, or a real model never sends them.
    analyze_prompt = fake_llm.calls[1]
    for key in ("issue", "rule", "conclusion"):
        assert key in analyze_prompt


@pytest.mark.asyncio
async def test_a_model_that_omits_the_split_leaves_it_empty(
    fake_retrieved_passages: list[dict],
) -> None:
    """No invented black-letter law: an absent field stays absent."""
    fake_llm = FakeOllama(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "Prose only.", "citations": [], "confidence": 0.4}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: fake_llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("q?")
    assert (result.issue, result.rule, result.conclusion) == ("", "", "")


# ---------------------------------------------------------------------------
# Streaming the analyze pass (BL-20260905-11)
# ---------------------------------------------------------------------------


class _StreamingLLM:
    """A chain double that can stream, like ChatProviderChain."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.streamed: list[str] = []
        self.buffered: list[str] = []

    async def ainvoke(self, prompt: str) -> _FakeMessage:
        self.buffered.append(prompt)
        return _FakeMessage(self._responses.pop(0))

    async def astream(self, prompt: str):
        self.streamed.append(prompt)
        text = self._responses.pop(0)
        for i in range(0, len(text), 8):
            yield _FakeMessage(text[i : i + 8])


@pytest.mark.asyncio
async def test_analyze_streams_deltas_to_the_sink(
    fake_retrieved_passages: list[dict],
) -> None:
    """With a sink the answer arrives as it is written, not after."""
    answer = '{"answer": "Marbury established judicial review.", "citations": [], "confidence": 0.6}'
    llm = _StreamingLLM(['{"queries": ["q"], "rationale": "ok"}', answer])
    seen: list[str] = []

    async def sink(text: str) -> None:
        seen.append(text)

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
        on_delta=sink,
    )
    result = await wf.invoke("q?")

    assert "judicial review" in result.answer
    assert len(seen) > 1  # streamed, not one buffered blob
    assert "".join(seen) == answer
    # Only the long pass streams; query drafting stays buffered.
    assert len(llm.streamed) == 1
    assert len(llm.buffered) == 1


@pytest.mark.asyncio
async def test_without_a_sink_the_node_stays_buffered(
    fake_retrieved_passages: list[dict],
) -> None:
    llm = _StreamingLLM(
        [
            '{"queries": ["q"], "rationale": "ok"}',
            '{"answer": "a", "citations": [], "confidence": 0.5}',
        ]
    )

    async def fake_resolver(citations: list[str]) -> dict[str, str | None]:
        return {}

    async def fake_retriever(state):
        return fake_retrieved_passages

    wf = LegalWorkflow(
        llm_factory=lambda: llm,
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result = await wf.invoke("q?")
    assert result.answer == "a"
    assert llm.streamed == []
    assert len(llm.buffered) == 2
