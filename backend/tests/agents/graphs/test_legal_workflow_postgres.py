"""Postgres-backed resilience integration test (spec 010 T-007 / AC-3).

Skipped automatically unless:

  - The `local-ai` extra is installed (`langgraph` + `langgraph-checkpoint-postgres`).
  - `LANGGRAPH_INTEGRATION=1` is set in the environment (gates network calls).
  - `settings.POSTGRES_URL` points at a reachable Postgres.

Run locally with:

    make local-ai-up
    LANGGRAPH_INTEGRATION=1 pytest -m integration \
      backend/tests/agents/graphs/test_legal_workflow_postgres.py -q
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langgraph.checkpoint.postgres")

if not os.getenv("LANGGRAPH_INTEGRATION"):
    pytest.skip(
        "LANGGRAPH_INTEGRATION not set; integration test opt-in only",
        allow_module_level=True,
    )

from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflow
from law_ai.agents_runtime.checkpointer import ensure_schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = text


class FakeOllama:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def ainvoke(self, prompt: str) -> _FakeMessage:
        return _FakeMessage(self._responses.pop(0) if self._responses else "{}")


async def test_workflow_state_survives_restart() -> None:
    """AC-3: a fresh LegalWorkflow instance can resume the same thread_id."""
    await ensure_schema()  # idempotent setup of checkpointer tables

    canned = [
        '{"queries": ["q"]}',
        '{"answer": "ok", "citations": [], "confidence": 0.6}',
    ]

    async def fake_resolver(citations):
        return {}

    async def fake_retriever(state):
        return [
            {
                "title": "Test Case",
                "snippet": "Snippet.",
                "source_url": "https://example.test/case",
            }
        ]

    thread_id = "lwf-resilience-001"

    wf1 = LegalWorkflow(
        llm_factory=lambda: FakeOllama(canned),
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    result1 = await wf1.invoke("q", thread_id=thread_id)
    assert result1.langgraph_thread_id == thread_id

    # Simulate process restart by building a brand-new instance.
    wf2 = LegalWorkflow(
        llm_factory=lambda: FakeOllama([]),
        cite_resolver=fake_resolver,
        retriever=fake_retriever,
    )
    state = await wf2.get_state(thread_id)
    assert state is not None, "checkpointer should rehydrate the thread"
    values = getattr(state, "values", state)
    assert values.get("answer") == result1.answer
