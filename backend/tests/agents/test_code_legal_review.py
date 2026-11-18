"""``CodeLegalReview`` as a registered agent (spec 057 §10, AGENTS.md rules).

The graph's behaviour is pinned in ``tests/lawmode/test_code_legal_review.py``;
this file holds the agent contract: registered, ``run(input) -> structured
output``, ``human_approval_required`` declared, the graph shape spec 057 §10
names, and every call on the provider chain. No LegalBench case: spec 057 §12
records no LegalBench impact, and no LegalBench task covers source-code
review.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from law_ai.agents_runtime.graphs import code_legal_review as mod
from law_ai.lawmode.schemas import ReviewResult
from tests.lawmode.conftest import StubProvider, chain

pytestmark = pytest.mark.unit


class _Queue:
    async def __call__(self, risk: Any, **_: Any) -> str:
        return f"queue:{risk.id}"


def test_it_is_registered_with_the_agents_runtime() -> None:
    from law_ai.agents_runtime import registry

    registry.register_all_agents()

    assert registry.AGENT_REGISTRY["CodeLegalReview"] is mod.CodeLegalReview


def test_it_declares_the_agent_surface() -> None:
    agent = mod.CodeLegalReview(enqueue=_Queue())

    assert agent.name == "CodeLegalReview"
    assert agent.human_approval_required is True
    assert "human review queue" in agent.description


def test_the_graph_is_the_eight_chains_then_aggregate_then_hitl() -> None:
    graph = mod.build_code_legal_review_graph(mod.CodeLegalReview(enqueue=_Queue()))

    nodes = [name for name in graph.get_graph().nodes if not name.startswith("__")]
    assert nodes == [spec.name for spec in mod.CHAINS] + ["aggregate", "hitl"]
    assert [spec.name for spec in mod.REVIEW_CHAINS] == [
        "privacy",
        "licence",
        "security",
        "accessibility",
        "copyright",
        "regulatory",
    ]


async def test_run_returns_a_structured_report_from_the_chain() -> None:
    provider = StubProvider(text='{"jurisdictions": [], "domain": "", "risks": []}')

    with chain(provider):
        review = await mod.CodeLegalReview(enqueue=_Queue()).run(
            {"code": "print('hello')", "file_path": "hello.py"}
        )

    assert isinstance(review, ReviewResult)
    assert len(provider.requests) == len(mod.CHAINS)
    assert review.risks == []
    assert review.chains_not_run == []
    assert review.metadata["graph"] == "code_legal_review"


async def test_run_refuses_an_input_with_no_code() -> None:
    with pytest.raises(ValidationError):
        await mod.CodeLegalReview(enqueue=_Queue()).run({"code": ""})
