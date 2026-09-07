"""The optional audited LLM holding-summary pass (BL-20260906-01).

``ExtractionResult.holding_summary_kind`` reserved ``"summary"`` for prose a
model wrote, but ``IngestionScout.extract`` is sync and had no way to make the
call, so only the rule-based ``"excerpt"`` was ever produced. ``aextract`` is
the async variant that can.

No model is ever called here: ``law_ai.core.llm.agenerate`` is stubbed, which
is also the point of the flag — it is off unless an operator turns it on.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core import llm as llm_module
from law_ai.ingestionapp.services import scout as scout_module
from law_ai.ingestionapp.services.scout import IngestionScout
from tests.ingestion.test_scout import HIGH_CONF_OPINION

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


def _stub(monkeypatch: pytest.MonkeyPatch, text: str) -> list[dict[str, Any]]:
    """Record every call the pass would make to the provider chain."""
    calls: list[dict[str, Any]] = []

    async def fake_agenerate(prompt: str, **kwargs: Any) -> _Result:
        calls.append({"prompt": prompt, **kwargs})
        return _Result(text)

    monkeypatch.setattr(llm_module, "agenerate", fake_agenerate)
    return calls


@pytest.mark.asyncio
async def test_flag_off_keeps_the_deterministic_excerpt(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.INGEST_LLM_SUMMARY = False
    calls = _stub(monkeypatch, "should never be used")

    result = await IngestionScout().aextract(HIGH_CONF_OPINION)

    assert calls == [], "the pass must not call a model while the flag is off"
    assert result.holding_summary_kind == "excerpt"


@pytest.mark.asyncio
async def test_flag_on_writes_a_labelled_model_summary(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.INGEST_LLM_SUMMARY = True
    calls = _stub(monkeypatch, "  The court held that the statute is  valid. ")

    result = await IngestionScout().aextract(HIGH_CONF_OPINION)

    assert result.holding_summary == "The court held that the statute is valid."
    # The label is load-bearing: a prompt must be able to tell a model summary
    # from a verbatim excerpt.
    assert result.holding_summary_kind == "summary"
    assert len(calls) == 1
    # Routed through law_ai.core.llm, so the llm_call provenance event is
    # written by the router rather than bypassed here.
    assert calls[0]["agent"] == "IngestionScout"
    assert "OPINION:" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_a_provider_outage_falls_back_to_the_excerpt(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.INGEST_LLM_SUMMARY = True
    excerpt = IngestionScout().extract(HIGH_CONF_OPINION).holding_summary

    async def boom(prompt: str, **kwargs: Any) -> _Result:
        raise RuntimeError("no provider reachable")

    monkeypatch.setattr(llm_module, "agenerate", boom)

    result = await IngestionScout().aextract(HIGH_CONF_OPINION)

    assert result.holding_summary == excerpt
    assert result.holding_summary_kind == "excerpt"


@pytest.mark.asyncio
async def test_an_empty_answer_is_a_refusal_not_a_summary(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0004 P3: a silent record must not acquire a made-up holding."""
    settings.INGEST_LLM_SUMMARY = True
    _stub(monkeypatch, "   ")

    result = await IngestionScout().aextract(HIGH_CONF_OPINION)

    assert result.holding_summary_kind == "excerpt"


@pytest.mark.asyncio
async def test_the_prompt_input_is_bounded(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.INGEST_LLM_SUMMARY = True
    calls = _stub(monkeypatch, "Held: affirmed.")
    huge = dict(HIGH_CONF_OPINION, plain_text="word " * 20_000)

    await IngestionScout().aextract(huge)

    body = calls[0]["prompt"].split("OPINION:\n", 1)[1]
    assert len(body) <= scout_module.LLM_SUMMARY_INPUT_CHARS


@pytest.mark.asyncio
async def test_a_bodyless_payload_never_calls_the_model(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.INGEST_LLM_SUMMARY = True
    calls = _stub(monkeypatch, "Held: affirmed.")

    await IngestionScout().aextract({"id": "no-body", "case_name": "Doe v. Roe"})

    assert calls == []
