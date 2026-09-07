"""The matter boost has to be reachable from a product path (BL-20260817-05).

``tests/agents/tools/test_graph_rag_boost.py`` covers the mechanism: given a
boost set, the retriever promotes it, labels it, and declares it in the
coverage envelope. That is worth nothing if no caller can supply the matter —
which was the state this file closes. Each test here pins one link in the
chain ``POST /api/analysis → LegalAnalyst → LegalWorkflow.invoke → retriever
state``, plus the two guards that chain needs: the caller must own the matter,
and the bias must come back to them as structured data.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model

from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflow, RetrievalStats

pytestmark = [pytest.mark.unit]


class _Recorder:
    """A retriever stand-in that captures the state the workflow hands it."""

    def __init__(self, coverage: Any = None) -> None:
        self.states: list[dict[str, Any]] = []
        self.last_coverage = coverage

    async def __call__(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self.states.append(dict(state))
        return []


class _Coverage:
    lexical_count = 1
    expanded_count = 0
    jurisdictions_present = ["US"]
    jurisdiction_absent = False
    date_earliest = None
    date_latest = None
    boosted_count = 3
    boost_source = "matter:lease-dispute"

    def note(self) -> str:
        return "3 passage(s) ranked first because this matter verified them."


def _stub_llm() -> Any:
    class _Reply:
        content = '{"queries": ["q"], "rationale": "r"}'

    class _LLM:
        async def ainvoke(self, prompt: str) -> Any:
            return _Reply()

    return _LLM()


# ---------------------------------------------------------------------------
# LegalWorkflow.invoke — the only public entry point
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invoke_seeds_the_matter_into_retriever_state() -> None:
    """Without this the `matter_id` TypedDict field is unreachable."""
    recorder = _Recorder()
    workflow = LegalWorkflow(llm_factory=_stub_llm, retriever=recorder)

    await workflow.invoke("Is the lease enforceable?", matter_id=42)

    assert recorder.states, "retriever was never called"
    assert recorder.states[0]["matter_id"] == 42


@pytest.mark.asyncio
async def test_invoke_without_a_matter_stays_matter_blind() -> None:
    recorder = _Recorder()
    workflow = LegalWorkflow(llm_factory=_stub_llm, retriever=recorder)

    await workflow.invoke("Is the lease enforceable?")

    assert "matter_id" not in recorder.states[0]


@pytest.mark.asyncio
async def test_the_boost_is_reported_in_the_structured_envelope() -> None:
    """`coverage_note` prose is not enough — a caller must be able to check it."""
    recorder = _Recorder(coverage=_Coverage())
    workflow = LegalWorkflow(llm_factory=_stub_llm, retriever=recorder)

    result = await workflow.invoke("Is the lease enforceable?", matter_id=42)

    assert result.retrieval_stats.boosted_count == 3
    assert result.retrieval_stats.boost_source == "matter:lease-dispute"


def test_retrieval_stats_defaults_to_no_boost() -> None:
    stats = RetrievalStats()
    assert stats.boosted_count == 0
    assert stats.boost_source == ""


# ---------------------------------------------------------------------------
# LegalAnalyst — the crew member the API actually runs
# ---------------------------------------------------------------------------
async def _capture_invoke_kwargs(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    """Run the analyst's LangGraph path and return the kwargs it passed on."""
    pytest.importorskip("langgraph")
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from law_ai.agents_runtime.crews import legal_analyst as mod
    from law_ai.agents_runtime.graphs.legal_workflow import (
        LegalWorkflow as _RealWorkflow,
    )
    from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflowOutput

    seen: dict[str, Any] = {}

    async def fake_invoke(self: Any, question: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return LegalWorkflowOutput(answer="a", confidence=0.5)

    @asynccontextmanager
    async def fake_saver() -> Any:
        yield None

    async def fake_ready() -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(_RealWorkflow, "invoke", fake_invoke)
    monkeypatch.setattr(mod, "_analysis_checkpointer", fake_saver)
    monkeypatch.setattr(mod, "_engine_ready", fake_ready)
    with patch.object(mod.provenance, "log_agent_call", return_value="t"):
        await mod.LegalAnalyst().run(payload)
    return seen


@pytest.mark.asyncio
async def test_the_analyst_forwards_the_matter_to_the_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = await _capture_invoke_kwargs(
        monkeypatch,
        {"text": "Is the lease enforceable?", "use_langgraph": True, "matter_id": 7},
    )
    assert seen["matter_id"] == 7


@pytest.mark.asyncio
async def test_the_analyst_sends_no_matter_when_the_caller_named_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = await _capture_invoke_kwargs(
        monkeypatch, {"text": "Is the lease enforceable?", "use_langgraph": True}
    )
    assert seen["matter_id"] is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(7, 7), ("7", 7), (None, None), ("", None), (0, None), (-1, None), ("x", None)],
)
def test_matter_ids_from_a_loose_payload_are_coerced(
    raw: Any, expected: int | None
) -> None:
    from law_ai.agents_runtime.crews.legal_analyst import _coerce_matter_id

    assert _coerce_matter_id(raw) == expected


# ---------------------------------------------------------------------------
# POST /api/analysis — ownership is proved before the id is honoured
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_the_api_accepts_a_matter_the_caller_owns() -> None:
    from rest_framework.test import APIClient

    from law_ai.matters.models import Matter

    user = get_user_model().objects.create_user(username="ada", password="pw-1843x")
    matter = Matter.objects.create(owner=user, name="Lease", slug="lease")

    client = APIClient()
    client.force_login(user)
    res = client.post(
        "/api/analysis",
        {
            "text": "Is the lease enforceable?",
            "use_langgraph": False,
            "matter_id": matter.pk,
        },
        format="json",
    )
    assert res.status_code == 200


@pytest.mark.django_db
def test_someone_elses_matter_is_a_404_not_a_boost() -> None:
    """The boost set is another account's verified work — never leak it."""
    from rest_framework.test import APIClient

    from law_ai.matters.models import Matter

    owner = get_user_model().objects.create_user(username="ada", password="pw-1843x")
    other = get_user_model().objects.create_user(username="bob", password="pw-1843y")
    matter = Matter.objects.create(owner=owner, name="Lease", slug="lease")

    client = APIClient()
    client.force_login(other)
    res = client.post(
        "/api/analysis",
        {
            "text": "Is the lease enforceable?",
            "use_langgraph": False,
            "matter_id": matter.pk,
        },
        format="json",
    )
    assert res.status_code == 404


@pytest.mark.django_db
def test_an_anonymous_caller_cannot_name_a_matter() -> None:
    from rest_framework.test import APIClient

    res = APIClient().post(
        "/api/analysis",
        {"text": "Is the lease enforceable?", "use_langgraph": False, "matter_id": 1},
        format="json",
    )
    assert res.status_code == 401


@pytest.mark.django_db
def test_the_matterless_request_shape_is_unchanged() -> None:
    from rest_framework.test import APIClient

    res = APIClient().post(
        "/api/analysis",
        {"text": "Is the lease enforceable?", "use_langgraph": False},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["irac"]["retrieval"] is None or isinstance(
        res.json()["irac"]["retrieval"], dict
    )
