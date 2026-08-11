"""Tests for LegalAnalyst, including the dev-time Claude Code IRAC path."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


def _irac_payload(confidence: float = 0.85) -> str:
    return json.dumps(
        {
            "issue": "Whether a clickwrap arbitration clause is enforceable.",
            "rule": "Clickwrap terms bind a user given reasonable notice and assent.",
            "application": "Here, the terms were linked beside the sign-up button…",
            "conclusion": "Likely enforceable if notice was reasonably conspicuous.",
            "key_authorities": ["Specht v. Netscape", "Meyer v. Uber"],
            "confidence": confidence,
        }
    )


def _llm_result(
    text: str, *, provider: str = "claude_code", model: str = "claude-opus-5"
):
    """Build the LLMResult the provider chain hands back."""
    from law_ai.core.llm.base import LLMResult

    return LLMResult(text=text, provider=provider, model=model, latency_ms=1.0)


class TestDefaultPath:
    @pytest.mark.asyncio
    async def test_degrades_honestly_when_no_provider_is_reachable(self) -> None:
        """A dead chain fabricates nothing: degraded, confidence 0, HITL forced.

        Spec 034 replaced the old hardcoded "not implemented" path — the
        non-LangGraph route now runs the real chain — but the constitution
        §4/§13 guarantee is unchanged: never invent analysis, never attribute
        a degraded row to a real model.
        """
        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.core import llm as llm_pkg

        agent = mod.LegalAnalyst()
        boom = AsyncMock(side_effect=llm_pkg.LLMUnavailableError("all providers down"))
        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await agent.run({"question": "Is a clickwrap clause binding?"})
        assert out.degraded is True
        assert out.requires_review is True
        assert out.confidence == 0.0
        assert out.sources == []  # never invent authorities
        assert "OFFLINE FALLBACK" in out.rule
        # The audit trail must not attribute this to a real model.
        assert log.call_args.kwargs["model"] == "fallback/offline"


class TestLangGraphDefaultEngine:
    """Spec 027: LangGraph is the default engine with a resilience boundary."""

    @pytest.mark.asyncio
    async def test_probe_failure_degrades_instead_of_raising(self) -> None:
        from law_ai.agents_runtime import llm
        from law_ai.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                llm, "ollama_available_async", new=AsyncMock(return_value=False)
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await agent.run({"text": "Is X liable?", "use_langgraph": True})
        assert out.degraded is True
        assert out.requires_review is True
        assert out.confidence == 0.0
        assert "ENGINE UNAVAILABLE" in out.rule
        assert log.call_args.kwargs["model"] == "fallback/offline"

    @pytest.mark.asyncio
    async def test_workflow_crash_degrades_instead_of_raising(self) -> None:
        from law_ai.agents_runtime import llm
        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.agents_runtime.graphs import LegalWorkflow

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                llm, "ollama_available_async", new=AsyncMock(return_value=True)
            ),
            patch.object(
                LegalWorkflow, "invoke", new=AsyncMock(side_effect=OSError("boom"))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await agent.run({"text": "Is X liable?", "use_langgraph": True})
        assert out.degraded is True
        assert out.confidence == 0.0
        assert "OSError" in out.rule
        assert log.call_args.kwargs["model"] == "fallback/offline"

    def test_analysis_request_defaults_to_langgraph(self) -> None:
        from law_ai.analysis.urls import AnalysisRequest

        assert AnalysisRequest(text="x").use_langgraph is True


class TestViaProviderChain:
    """The non-LangGraph path routes through the shared provider chain."""

    @pytest.mark.asyncio
    async def test_uses_the_provider_the_chain_selected(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_irac_payload())),
            ),
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-cc"
            ) as log,
        ):
            out = await agent.run({"question": "Is a clickwrap clause enforceable?"})
        assert "clickwrap" in out.issue.lower()
        assert [s["title"] for s in out.sources] == [
            "Specht v. Netscape",
            "Meyer v. Uber",
        ]
        assert out.confidence == 0.85
        assert out.trace_id == "trace-cc"
        assert log.call_args.kwargs["model"] == "claude_code/claude-opus-5"

    @pytest.mark.asyncio
    async def test_audit_records_the_tier_that_actually_served(self) -> None:
        """After a fallback the trail must name Ollama, not the tier we wanted."""
        from law_ai.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        fell_back = _llm_result(
            _irac_payload(), provider="ollama", model="mistral:7b-instruct-q4_K_M"
        )
        with (
            patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=fell_back)),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            await agent.run({"question": "x"})
        assert log.call_args.kwargs["model"] == "ollama/mistral:7b-instruct-q4_K_M"

    @pytest.mark.asyncio
    async def test_clamps_out_of_range_confidence(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_irac_payload(confidence=9.0))),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"question": "x"})
        assert out.confidence == 1.0

    @pytest.mark.asyncio
    async def test_degrades_to_offline_on_provider_error(self) -> None:
        import httpx

        from law_ai.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        boom = AsyncMock(side_effect=httpx.ConnectError("overloaded"))
        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await agent.run({"question": "Is X liable?"})
        assert out.confidence == 0.0
        assert "OFFLINE FALLBACK" in out.rule
        assert log.call_args.kwargs["model"] == "fallback/offline"
