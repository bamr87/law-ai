"""Postgres-backed resilience integration test (spec 010 T-007 / AC-3).

Skipped automatically unless:

  - `langgraph` + `langgraph-checkpoint-postgres` are importable. Both are core
    backend dependencies now (`backend/pyproject.toml`), so `.[dev,test]` is
    enough — the `local-ai` extra is Phoenix/OTel only.
  - `LANGGRAPH_INTEGRATION=1` is set in the environment (opt-in gate).
  - `settings.POSTGRES_URL` points at a reachable Postgres.

No LLM is reached: the workflow is built with :class:`FakeOllama`, so the only
live dependency is Postgres.

Runs in CI in the "Integration Tests" workflow
(`.github/workflows/integration-tests.yml`), which starts Postgres and sets
`LANGGRAPH_INTEGRATION=1` plus a localhost `POSTGRES_URL` (BL-20260502-08).

Run locally with:

    make test-integration
    # or, targeted:
    LANGGRAPH_INTEGRATION=1 pytest -m integration \
      backend/tests/agents/graphs/test_legal_workflow_postgres.py -q --no-cov
"""

from __future__ import annotations

import os
import secrets

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
from law_ai.agents_runtime.graphs.runtime import build_checkpointer

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
    """AC-3: a fresh LegalWorkflow instance can resume the same thread_id.

    The two instances each open their *own* ``AsyncPostgresSaver`` connection,
    which is what makes this a restart rather than a shared-object handoff:
    the only thing they have in common is the Postgres database behind
    ``settings.POSTGRES_URL``.
    """
    status = await ensure_schema()  # idempotent setup of checkpointer tables
    assert status.ok, f"checkpointer schema unavailable: {status.detail}"

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

    # Fresh id per run: a fixed one would let a leftover row from a previous
    # run satisfy the assertion even if this run persisted nothing.
    thread_id = f"lwf-resilience-{secrets.token_hex(6)}"

    async with build_checkpointer("postgres") as saver1:
        wf1 = LegalWorkflow(
            llm_factory=lambda: FakeOllama(canned),
            cite_resolver=fake_resolver,
            retriever=fake_retriever,
            checkpointer=saver1,
        )
        result1 = await wf1.invoke("q", thread_id=thread_id)
    assert result1.langgraph_thread_id == thread_id

    # Simulate process restart: new instance, new saver, new connection.
    async with build_checkpointer("postgres") as saver2:
        wf2 = LegalWorkflow(
            llm_factory=lambda: FakeOllama([]),
            cite_resolver=fake_resolver,
            retriever=fake_retriever,
            checkpointer=saver2,
        )
        state = await wf2.get_state(thread_id)
    assert state is not None, "checkpointer should rehydrate the thread"
    values = getattr(state, "values", state)
    assert values.get("answer") == result1.answer
