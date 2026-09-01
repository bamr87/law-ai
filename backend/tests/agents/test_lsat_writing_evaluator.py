"""Tests for the LSATWritingEvaluator crew (spec 047 T-003, AC-4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from django.conf import settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _prompt_and_rubric() -> tuple[Any, Any]:
    from law_ai.lsat.services.writing import load_writing_prompts, rubric_for

    prompt = next(iter(load_writing_prompts().values()))
    return prompt, rubric_for(prompt)


def _draft(words: int = 120) -> str:
    return (
        "The council should fund the rail extension because it reaches people "
        "who cannot drive. " * words
    )[:4000]


def _payload(bands: dict[str, int] | None = None, **overrides: Any) -> str:
    _, rubric = _prompt_and_rubric()
    bands = bands or {}
    body: dict[str, Any] = {
        "position_taken": "rail",
        "summary": "Clear position, thin counterargument.",
        "criteria": [
            {
                "criterion_id": c.id,
                "band": bands.get(c.id, 3),
                "evidence": "the only option that reaches people who cannot drive",
                "improvement": "State the standard explicitly in paragraph two.",
            }
            for c in rubric.criteria
        ],
        "strengths": ["clear thesis"],
        "priorities": ["answer the cost objection"],
    }
    body.update(overrides)
    return json.dumps({"evaluation": body})


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model_label = "test/model"


# ---------------------------------------------------------------------------
# AC-4 — the run() contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_scores_every_rubric_criterion() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(_payload()))
    ):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )

    assert out.degraded is False
    assert out.model == "test/model"
    assert out.prompt_version.startswith("lsat_writing_evaluator/")
    assert out.confidence > 0.0
    assert [c.criterion_id for c in out.evaluation.criteria] == list(
        rubric.criterion_ids
    )
    assert out.evaluation.prompt_id == prompt.id
    assert out.evaluation.rubric_id == rubric.id
    assert out.evaluation.weighted_band == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_weighted_band_follows_rubric_weights() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    heaviest = max(rubric.criteria, key=lambda c: c.weight)
    lightest = min(rubric.criteria, key=lambda c: c.weight)
    raw = _payload(bands={heaviest.id: 4, lightest.id: 1})
    with patch.object(llm, "agenerate", new=AsyncMock(return_value=_Result(raw))):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )

    expected = sum(
        (4 if c.id == heaviest.id else 1 if c.id == lightest.id else 3) * c.weight
        for c in rubric.criteria
    )
    assert out.evaluation.weighted_band == pytest.approx(round(expected, 2))


@pytest.mark.asyncio
async def test_criteria_are_reordered_to_the_rubric() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    body = json.loads(_payload())
    body["evaluation"]["criteria"].reverse()
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(json.dumps(body)))
    ):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )
    assert [c.criterion_id for c in out.evaluation.criteria] == list(
        rubric.criterion_ids
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw, why",
    [
        ("not json at all", "unparseable"),
        (json.dumps({"nope": {}}), "missing evaluation object"),
    ],
)
async def test_unusable_response_degrades(raw: str, why: str) -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    with patch.object(llm, "agenerate", new=AsyncMock(return_value=_Result(raw))):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )
    assert out.degraded is True, why
    assert len(out.evaluation.criteria) == len(rubric.criteria)


@pytest.mark.asyncio
async def test_partial_scoring_is_rejected_not_shown() -> None:
    # A reading that silently skips a criterion looks complete to a learner.
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, _ = _prompt_and_rubric()
    body = json.loads(_payload())
    body["evaluation"]["criteria"].pop()
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(json.dumps(body)))
    ):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )
    assert out.degraded is True


@pytest.mark.asyncio
async def test_band_outside_the_rubric_is_rejected() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    body = json.loads(_payload())
    body["evaluation"]["criteria"][0]["band"] = max(rubric.band_levels) + 5
    with patch.object(
        llm, "agenerate", new=AsyncMock(return_value=_Result(json.dumps(body)))
    ):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )
    assert out.degraded is True


@pytest.mark.asyncio
async def test_unknown_position_is_reported_as_unclear_not_invented() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, _ = _prompt_and_rubric()
    raw = _payload(position_taken="a-position-that-does-not-exist")
    with patch.object(llm, "agenerate", new=AsyncMock(return_value=_Result(raw))):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )
    assert out.degraded is False
    assert out.evaluation.position_taken is None


@pytest.mark.asyncio
async def test_offline_fallback_when_no_provider_is_reachable() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, rubric = _prompt_and_rubric()
    with patch.object(
        llm,
        "agenerate",
        new=AsyncMock(side_effect=llm.LLMUnavailableError("no providers")),
    ):
        out = await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )

    assert out.degraded is True
    assert out.confidence == 0.0
    assert out.model == "fallback/offline"
    assert "OFFLINE FALLBACK" in out.evaluation.summary
    assert len(out.evaluation.criteria) == len(rubric.criteria)
    assert all(c.band == min(rubric.band_levels) for c in out.evaluation.criteria)


@pytest.mark.asyncio
async def test_unknown_prompt_raises() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )

    with pytest.raises(KeyError):
        await LSATWritingEvaluator().run(
            {"prompt_id": "no-such-prompt", "response": _draft()}
        )


@pytest.mark.asyncio
async def test_too_short_a_response_is_rejected_before_a_model_call() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.core import llm

    prompt, _ = _prompt_and_rubric()
    call = AsyncMock()
    with patch.object(llm, "agenerate", new=call), pytest.raises(ValidationError):
        await LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": "too short"}
        )
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_logs_one_agent_call_with_provenance() -> None:
    from law_ai.agents_runtime.crews import lsat_writing_evaluator as mod
    from law_ai.core import llm

    prompt, _ = _prompt_and_rubric()
    with (
        patch.object(llm, "agenerate", new=AsyncMock(return_value=_Result(_payload()))),
        patch.object(
            mod.provenance, "log_agent_call", return_value="trace-1"
        ) as logged,
    ):
        out = await mod.LSATWritingEvaluator().run(
            {"prompt_id": prompt.id, "response": _draft()}
        )

    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["agent_name"] == "LSATWritingEvaluator"
    assert kwargs["model"] == "test/model"
    assert kwargs["input_data"]["prompt_id"] == prompt.id
    assert out.trace_id == "trace-1"


def test_agent_declares_the_hitl_gate() -> None:
    from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
        LSATWritingEvaluator,
    )
    from law_ai.agents_runtime.registry import register_all_agents, AGENT_REGISTRY

    assert LSATWritingEvaluator.human_approval_required is True
    register_all_agents()
    assert AGENT_REGISTRY["LSATWritingEvaluator"] is LSATWritingEvaluator
