"""Tests for the LLM provider chain (law_ai.core.llm).

The chain is the product runtime under constitution §1 as amended (spec 034):
Claude over OAuth, then Claude over an API key, then local Ollama. What matters
here is the *routing contract* — which provider serves, what happens when one
is unconfigured or failing, and that a total failure is an honest error rather
than an empty string. No real network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from law_ai.core import llm
from law_ai.core.llm.base import LLMRequest


class _StubProvider:
    """Minimal provider double honouring the LLMProvider protocol."""

    def __init__(
        self,
        name: str,
        *,
        configured: bool = True,
        text: str | None = "ok",
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._configured = configured
        self._text = text
        self._error = error
        self.calls = 0

    def configured(self) -> bool:
        return self._configured

    def unconfigured_reason(self) -> str | None:
        return None if self._configured else f"{self.name} not configured"

    def model_for(self, request: LLMRequest) -> str:
        return f"{self.name}-model"

    async def agenerate(self, request: LLMRequest) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text

    async def probe(self) -> dict[str, Any]:
        return {"reachable": self._error is None}


def _chain(*providers: _StubProvider):
    """Patch build_chain so routing runs against the given stubs, in order."""
    return patch("law_ai.core.llm.router.build_chain", return_value=providers)


# ---------------------------------------------------------------------------
# Chain resolution
# ---------------------------------------------------------------------------


class TestChainNames:
    def test_defaults_to_claude_first_ollama_last(self, settings) -> None:
        settings.LLM_PROVIDER_CHAIN = ""
        assert llm.chain_names() == ("claude_code", "anthropic_api", "ollama")

    def test_parses_configured_order(self, settings) -> None:
        settings.LLM_PROVIDER_CHAIN = "ollama, claude_code"
        assert llm.chain_names() == ("ollama", "claude_code")

    def test_pinning_a_single_provider(self, settings) -> None:
        """The escape hatch privileged-data deployments rely on."""
        settings.LLM_PROVIDER_CHAIN = "ollama"
        assert llm.chain_names() == ("ollama",)

    def test_unknown_provider_is_dropped_not_fatal(self, settings) -> None:
        """A typo must degrade to the known providers, not kill the runtime."""
        settings.LLM_PROVIDER_CHAIN = "clod_code,ollama"
        assert llm.chain_names() == ("ollama",)

    def test_all_unknown_falls_back_to_default(self, settings) -> None:
        settings.LLM_PROVIDER_CHAIN = "nonsense"
        assert llm.chain_names() == llm.DEFAULT_CHAIN

    def test_duplicates_keep_first_position(self, settings) -> None:
        settings.LLM_PROVIDER_CHAIN = "ollama,claude_code,ollama"
        assert llm.chain_names() == ("ollama", "claude_code")


# ---------------------------------------------------------------------------
# Routing + fallback
# ---------------------------------------------------------------------------


class TestRouting:
    async def test_first_configured_provider_serves(self) -> None:
        first = _StubProvider("claude_code", text="from claude")
        second = _StubProvider("ollama", text="from ollama")

        with _chain(first, second):
            result = await llm.agenerate("q")

        assert result.text == "from claude"
        assert result.provider == "claude_code"
        assert result.model_label == "claude_code/claude_code-model"
        assert result.fell_back is False
        assert second.calls == 0

    async def test_skips_unconfigured_provider(self) -> None:
        first = _StubProvider("claude_code", configured=False)
        second = _StubProvider("ollama", text="local")

        with _chain(first, second):
            result = await llm.agenerate("q")

        assert result.provider == "ollama"
        assert result.fell_back is True
        assert first.calls == 0
        skipped = next(a for a in result.attempts if a.provider == "claude_code")
        assert skipped.ok is False
        assert skipped.skipped_reason == "claude_code not configured"

    async def test_falls_through_on_provider_failure(self) -> None:
        first = _StubProvider("claude_code", error=TimeoutError("overloaded"))
        second = _StubProvider("anthropic_api", error=OSError("down"))
        third = _StubProvider("ollama", text="local")

        with _chain(first, second, third):
            result = await llm.agenerate("q")

        assert result.text == "local"
        assert result.provider == "ollama"
        assert result.fell_back is True
        assert [a.provider for a in result.attempts] == [
            "claude_code",
            "anthropic_api",
            "ollama",
        ]
        assert "TimeoutError" in (result.attempts[0].error or "")

    async def test_total_failure_raises_with_every_reason(self) -> None:
        """Constitution §13: an unavailable chain is a refusal, not an answer."""
        first = _StubProvider("claude_code", configured=False)
        second = _StubProvider("ollama", error=OSError("connection refused"))

        with _chain(first, second), pytest.raises(llm.LLMUnavailableError) as exc:
            await llm.agenerate("q")

        assert "claude_code" in str(exc.value)
        assert "connection refused" in str(exc.value)
        assert len(exc.value.attempts) == 2

    async def test_empty_chain_raises(self) -> None:
        with _chain(), pytest.raises(llm.LLMUnavailableError):
            await llm.agenerate("q")

    async def test_request_can_restrict_the_chain(self, settings) -> None:
        """`providers=` is how the eval/factory paths stay reproducible."""
        settings.LLM_PROVIDER_CHAIN = "claude_code,ollama"
        assert llm.chain_names(["ollama"]) == ("ollama",)

    async def test_per_provider_model_override(self) -> None:
        request = LLMRequest(prompt="q", models={"ollama": "mistral"})
        assert request.model_for("ollama") == "mistral"
        # A model id is meaningless to a provider it wasn't named for.
        assert request.model_for("claude_code") is None


# ---------------------------------------------------------------------------
# Provenance (constitution §5 — no LLM call bypasses the audit layer)
# ---------------------------------------------------------------------------


class TestProvenance:
    async def test_success_writes_llm_call_event(self) -> None:
        provider = _StubProvider("claude_code", text="hi")

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await llm.agenerate("q", agent="LegalAnalyst")

        log.assert_called_once()
        event_type, payload = log.call_args[0]
        assert event_type == "llm_call"
        assert payload["ok"] is True
        assert payload["agent"] == "LegalAnalyst"
        assert payload["provider"] == "claude_code"
        assert payload["model_label"] == "claude_code/claude_code-model"

    async def test_fallback_is_visible_in_the_audit_trail(self) -> None:
        first = _StubProvider("claude_code", error=OSError("down"))
        second = _StubProvider("ollama", text="local")

        with (
            _chain(first, second),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await llm.agenerate("q")

        payload = log.call_args[0][1]
        assert payload["fell_back"] is True
        assert payload["chain"] == ["claude_code", "ollama"]
        assert payload["attempts"][0]["ok"] is False

    async def test_total_failure_is_still_logged(self) -> None:
        provider = _StubProvider("ollama", error=OSError("down"))

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
            pytest.raises(llm.LLMUnavailableError),
        ):
            await llm.agenerate("q")

        assert log.call_args[0][1]["ok"] is False

    async def test_audit_failure_never_breaks_the_request(self) -> None:
        """A broken audit sink must not take the product down with it."""
        provider = _StubProvider("claude_code", text="hi")

        with (
            _chain(provider),
            patch(
                "law_ai.core.provenance.ProvenanceLogger.log_event",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            result = await llm.agenerate("q")

        assert result.text == "hi"


# ---------------------------------------------------------------------------
# Sync + runnable adapters
# ---------------------------------------------------------------------------


class TestAdapters:
    async def test_sync_generate_refuses_inside_an_event_loop(self) -> None:
        """Blocking the loop would stall every other request on the worker."""
        with pytest.raises(RuntimeError, match="sync-only"):
            llm.generate("q")

    async def test_chain_runnable_exposes_ainvoke(self) -> None:
        provider = _StubProvider("claude_code", text="graph answer")

        with _chain(provider):
            runnable = llm.build_runnable(agent="legal_workflow")
            assert await runnable.ainvoke("q") == "graph answer"
