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

from lawgraph.agents_runtime.graphs.legal_workflow import (
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
    assert result.human_approval_required is False  # nothing to verify
    assert len(fake_llm.calls) == 1  # only the retrieve call


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
