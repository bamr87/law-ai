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


class _FakeProvider:
    """Minimal stand-in for a chain provider used by the readiness gate."""

    def __init__(self, name: str, *, configured: bool = True) -> None:
        self.name = name
        self._configured = configured

    def configured(self) -> bool:
        return self._configured


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
        # BL-20260810-16: the UI needs the *kind* of degradation as data, not
        # as a prefix it has to parse — "start Ollama" is the wrong advice
        # here, where the whole chain failed.
        assert out.degraded_reason == "offline_fallback"
        # The audit trail must not attribute this to a real model.
        assert log.call_args.kwargs["model"] == "fallback/offline"


class TestLangGraphDefaultEngine:
    """Spec 027: LangGraph is the default engine with a resilience boundary."""

    @pytest.mark.asyncio
    async def test_probe_failure_degrades_instead_of_raising(self) -> None:
        """Ollama-only chain + Ollama down => honest refusal, never a 500."""
        from law_ai.agents_runtime import llm
        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.core import llm as core_llm

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                core_llm, "build_chain", return_value=[_FakeProvider("ollama")]
            ),
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
        # …whereas this one *is* fixed by starting the local engine
        # (BL-20260810-16).
        assert out.degraded_reason == "engine_unavailable"
        assert log.call_args.kwargs["model"] == "fallback/offline"

    @pytest.mark.asyncio
    async def test_claude_configured_runs_workflow_with_ollama_down(self) -> None:
        """BL-20260615-02: the Ollama probe must not gate a Claude-only box."""
        from law_ai.agents_runtime import llm
        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.agents_runtime.graphs import LegalWorkflow
        from law_ai.core import llm as core_llm

        probe = AsyncMock(return_value=False)
        agent = mod.LegalAnalyst()
        with (
            patch.object(
                core_llm,
                "build_chain",
                return_value=[_FakeProvider("claude_code"), _FakeProvider("ollama")],
            ),
            patch.object(llm, "ollama_available_async", new=probe),
            patch.object(
                LegalWorkflow, "invoke", new=AsyncMock(side_effect=OSError("boom"))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"text": "Is X liable?", "use_langgraph": True})

        # The probe was skipped entirely and the workflow was actually reached
        # (it then failed, which is the pre-existing resilience boundary).
        probe.assert_not_awaited()
        assert "OSError" in out.rule

    @pytest.mark.asyncio
    async def test_no_configured_provider_degrades(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.core import llm as core_llm

        agent = mod.LegalAnalyst()
        with (
            patch.object(
                core_llm,
                "build_chain",
                return_value=[_FakeProvider("claude_code", configured=False)],
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"text": "Is X liable?", "use_langgraph": True})
        assert out.degraded is True
        assert "no provider in LLM_PROVIDER_CHAIN is configured" in out.rule
        # The refusal names the chain, not just Ollama.
        assert "LLM_PROVIDER_CHAIN" in out.application

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


# ---------------------------------------------------------------------------
# BL-20260615-03: authority grounding on the direct-LLM path
# ---------------------------------------------------------------------------


class _FakeNameRetriever:
    """GraphRAG stand-in for the case-name fallback leg."""

    def __init__(self, by_title: dict[str, str] | None = None) -> None:
        self._by_title = by_title or {}
        self.queries: list[str] = []

    async def __call__(self, state):  # type: ignore[no-untyped-def]
        question = str(state.get("question") or "")
        self.queries.append(question)
        case_id = self._by_title.get(question)
        if case_id is None:
            return []
        return [{"id": case_id, "type": "Case", "title": question}]


class TestAuthorityGrounding:
    """The `use_langgraph=false` path must not present model names as sources."""

    async def _run(self, agent, mod):  # type: ignore[no-untyped-def]
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_irac_payload())),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            return await agent.run({"text": "Is a clickwrap clause binding?"})

    @pytest.mark.asyncio
    async def test_all_authorities_resolved_clears_review(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        async def resolver(names):  # type: ignore[no-untyped-def]
            return {n: f"case-{i}" for i, n in enumerate(names)}

        agent = mod.LegalAnalyst(
            cite_resolver=resolver, name_retriever=_FakeNameRetriever()
        )
        out = await self._run(agent, mod)

        assert [s["title"] for s in out.sources] == [
            "Specht v. Netscape",
            "Meyer v. Uber",
        ]
        assert all(s["verified"] for s in out.sources)
        assert all(s["resolved_case_id"] for s in out.sources)
        assert out.requires_review is False
        assert "Grounded 2/2 authorities" in out.reasoning_trace[-1]

    @pytest.mark.asyncio
    async def test_partial_resolution_keeps_review_pending(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        async def resolver(names):  # type: ignore[no-untyped-def]
            return {names[0]: "case-1", names[1]: None}

        agent = mod.LegalAnalyst(
            cite_resolver=resolver, name_retriever=_FakeNameRetriever()
        )
        out = await self._run(agent, mod)

        assert out.sources[0]["verified"] is True
        assert out.sources[1]["verified"] is False
        assert out.sources[1]["resolved_case_id"] is None
        assert out.requires_review is True
        assert "1 unresolved" in out.reasoning_trace[-1]

    @pytest.mark.asyncio
    async def test_name_lookup_grounds_what_the_alias_resolver_misses(self) -> None:
        """The prompt returns case *names*; aliases hold reporter citations."""
        from law_ai.agents_runtime.crews import legal_analyst as mod

        async def resolver(names):  # type: ignore[no-untyped-def]
            return dict.fromkeys(names)

        retriever = _FakeNameRetriever({"Meyer v. Uber": "meyer-v-uber"})
        agent = mod.LegalAnalyst(cite_resolver=resolver, name_retriever=retriever)
        out = await self._run(agent, mod)

        by_title = {s["title"]: s for s in out.sources}
        assert by_title["Meyer v. Uber"]["resolved_case_id"] == "meyer-v-uber"
        assert by_title["Meyer v. Uber"]["verified"] is True
        assert by_title["Specht v. Netscape"]["verified"] is False
        assert out.requires_review is True
        # Only the unresolved names hit the graph a second time.
        assert set(retriever.queries) == {"Specht v. Netscape", "Meyer v. Uber"}

    @pytest.mark.asyncio
    async def test_resolver_fault_degrades_without_raising(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        async def resolver(names):  # type: ignore[no-untyped-def]
            raise OSError("neo4j down")

        agent = mod.LegalAnalyst(
            cite_resolver=resolver, name_retriever=_FakeNameRetriever()
        )
        out = await self._run(agent, mod)

        assert out.requires_review is True
        assert "resolver unavailable" in out.reasoning_trace[-1].lower()
        # Nothing is upgraded to verified when the graph could not answer.
        assert all(not s.get("verified") for s in out.sources)

    @pytest.mark.asyncio
    async def test_no_authorities_still_forces_review(self) -> None:
        import json as _json

        from law_ai.agents_runtime.crews import legal_analyst as mod

        payload = _json.loads(_irac_payload())
        payload["key_authorities"] = []
        called = False

        async def resolver(names):  # type: ignore[no-untyped-def]
            nonlocal called
            called = True
            return {}

        agent = mod.LegalAnalyst(
            cite_resolver=resolver, name_retriever=_FakeNameRetriever()
        )
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_json.dumps(payload))),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"text": "Is a clickwrap clause binding?"})

        assert out.sources == []
        assert out.requires_review is True
        assert called is False
        assert "No authorities were named" in out.reasoning_trace[-1]

    @pytest.mark.asyncio
    async def test_default_resolver_is_the_shared_neo4j_helper(self) -> None:
        from law_ai.agents_runtime.crews import legal_analyst as mod

        assert mod.LegalAnalyst()._cite_resolver is mod._default_cite_resolver
