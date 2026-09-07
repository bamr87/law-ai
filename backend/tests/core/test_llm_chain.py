"""Tests for the LLM provider chain (law_ai.core.llm).

The chain is the product runtime under constitution §1 as amended (spec 034):
Claude over OAuth, then Claude over an API key, then local Ollama. What matters
here is the *routing contract* — which provider serves, what happens when one
is unconfigured or failing, and that a total failure is an honest error rather
than an empty string. No real network.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from law_ai.core import llm
from law_ai.core.llm import providers as llm_providers
from law_ai.core.llm import router
from law_ai.core.llm.base import LLMRequest
from law_ai.core.usage import LLMUsage, ProviderReply


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
        assert llm.chain_names() == ("claude_code", "anthropic_api", "xai", "ollama")

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


# ---------------------------------------------------------------------------
# Public surface (BL-20260905-12 — the package must export every provider)
# ---------------------------------------------------------------------------


class TestPublicSurface:
    """``law_ai.core.llm`` re-exports everything ``PROVIDER_REGISTRY`` knows.

    Spec 050 shipped ``XAI``/``XaiProvider`` half-exported and nothing failed;
    these assertions make the next provider fail loudly instead.
    """

    def test_every_registered_provider_class_is_exported(self) -> None:
        for cls in llm_providers.PROVIDER_REGISTRY.values():
            assert cls.__name__ in llm.__all__, f"{cls.__name__} missing from __all__"
            assert getattr(llm, cls.__name__) is cls

    def test_registry_keys_match_the_exported_name_constants(self) -> None:
        exported = {llm.CLAUDE_OAUTH, llm.ANTHROPIC_API, llm.XAI, llm.OLLAMA}
        assert set(llm_providers.PROVIDER_REGISTRY) == exported
        for constant in exported:
            # Each constant is the provider's own `name`, so a chain token and
            # the class agree on what to call the tier.
            assert llm_providers.PROVIDER_REGISTRY[constant].name == constant

    def test_registry_order_is_the_default_chain(self) -> None:
        assert tuple(llm_providers.PROVIDER_REGISTRY) == llm.DEFAULT_CHAIN

    def test_settings_default_parses_to_the_default_chain(self) -> None:
        """The django-environ default must agree with the router's constant."""
        from law_ai.settings import base as base_settings

        _cast, declared = base_settings.env.scheme["LLM_PROVIDER_CHAIN"]
        assert llm.chain_names(str(declared).split(",")) == llm.DEFAULT_CHAIN

    def test_package_docstring_names_every_tier(self) -> None:
        """The default-chain prose in the package docstring cannot go stale."""
        doc = llm.__doc__ or ""
        assert ",".join(llm.DEFAULT_CHAIN) in doc
        for name in llm_providers.PROVIDER_REGISTRY:
            assert name in doc

    def test_every_exported_name_resolves(self) -> None:
        for name in llm.__all__:
            assert hasattr(llm, name), f"__all__ lists {name!r} but it is missing"


# ---------------------------------------------------------------------------
# Token + cost accounting (BL-20260811-21 — hosted spend per agent)
# ---------------------------------------------------------------------------


class _UsageProvider(_StubProvider):
    """Stub that reports token usage the way a real transport does."""

    def __init__(self, name: str, *, usage: llm.LLMUsage | None, text: str = "ok"):
        super().__init__(name, text=text)
        self._usage = usage

    async def agenerate(self, request: LLMRequest) -> str:
        self.calls += 1
        return llm.ProviderReply(self._text or "", self._usage)


class TestTokenAccounting:
    """The ``llm_call`` event must carry tokens, and cost when priced."""

    async def test_result_and_event_carry_the_reported_tokens(self) -> None:
        provider = _UsageProvider(
            "claude_code", usage=llm.LLMUsage(input_tokens=120, output_tokens=45)
        )

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            result = await llm.agenerate("q", agent="LegalAnalyst")

        assert result.usage == llm.LLMUsage(input_tokens=120, output_tokens=45)
        payload = log.call_args[0][1]
        # Spend is attributable per agent: the agent name sits on the same event.
        assert payload["agent"] == "LegalAnalyst"
        assert payload["input_tokens"] == 120
        assert payload["output_tokens"] == 45
        assert payload["total_tokens"] == 165

    async def test_a_provider_without_usage_logs_nulls_not_a_failure(self) -> None:
        """Ollama-style silence must degrade to null counts, never an error."""
        provider = _StubProvider("ollama", text="local")

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            result = await llm.agenerate("q")

        assert result.text == "local"
        assert result.usage is None
        payload = log.call_args[0][1]
        assert payload["input_tokens"] is None
        assert payload["output_tokens"] is None
        assert payload["cost_usd"] is None

    async def test_cost_is_priced_from_the_settings_table(self, settings) -> None:
        settings.LLM_PRICE_TABLE = {
            "claude_code/claude_code-model": {
                "in_per_mtok": 5.0,
                "out_per_mtok": 25.0,
            }
        }
        provider = _UsageProvider(
            "claude_code",
            usage=llm.LLMUsage(input_tokens=1_000_000, output_tokens=200_000),
        )

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await llm.agenerate("q")

        assert log.call_args[0][1]["cost_usd"] == pytest.approx(10.0)

    async def test_unpriced_model_logs_tokens_with_a_null_cost(self, settings) -> None:
        settings.LLM_PRICE_TABLE = {"some/other-model": {"in_per_mtok": 5.0}}
        provider = _UsageProvider(
            "xai", usage=llm.LLMUsage(input_tokens=10, output_tokens=2)
        )

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await llm.agenerate("q")

        payload = log.call_args[0][1]
        assert payload["input_tokens"] == 10
        assert payload["cost_usd"] is None

    def test_price_lookup_falls_back_from_model_to_provider(self, settings) -> None:
        """A tier can be priced roughly without naming every model id."""
        settings.LLM_PRICE_TABLE = {"xai": {"in_per_mtok": 2.0, "out_per_mtok": 10.0}}
        usage = llm.LLMUsage(input_tokens=500_000, output_tokens=100_000)

        cost = llm.estimate_cost_usd("xai", "grok-4.6", usage)

        assert cost == pytest.approx(1.0 + 1.0)

    def test_estimate_cost_is_none_without_usage_or_prices(self, settings) -> None:
        settings.LLM_PRICE_TABLE = {}
        assert llm.estimate_cost_usd("xai", "grok-4.6", None) is None
        assert (
            llm.estimate_cost_usd("xai", "grok-4.6", llm.LLMUsage(input_tokens=5))
            is None
        )

    def test_a_malformed_price_row_never_raises(self, settings) -> None:
        settings.LLM_PRICE_TABLE = {"xai": {"in_per_mtok": "free"}}
        usage = llm.LLMUsage(input_tokens=10, output_tokens=1)

        assert llm.estimate_cost_usd("xai", "grok-4.6", usage) is None

    def test_partial_counts_are_kept(self) -> None:
        """One half of the usage block is better than discarding both."""
        usage = llm.LLMUsage.from_counts(None, 42)

        assert usage == llm.LLMUsage(input_tokens=None, output_tokens=42)
        assert usage is not None and usage.total_tokens == 42
        assert llm.LLMUsage.from_counts(None, None) is None
        assert llm.LLMUsage.from_counts("many", -3) is None

    def test_provider_reply_is_a_plain_string_to_callers(self) -> None:
        reply = llm.ProviderReply("hello", llm.LLMUsage(input_tokens=1))

        assert isinstance(reply, str)
        assert reply == "hello"
        assert llm.usage_of(reply) == llm.LLMUsage(input_tokens=1)
        assert llm.usage_of("hello") is None


# ---------------------------------------------------------------------------
# Permanent vs transient failures (BL-20260811-23)
# ---------------------------------------------------------------------------


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.HTTPStatusError(
        f"HTTP {status}",
        request=request,
        response=httpx.Response(status, request=request),
    )


@pytest.fixture(autouse=True)
def _forget_permanent_failures() -> Any:
    """The router's failure memory is per-process; keep tests independent."""
    llm.reset_permanent_failures()
    yield
    llm.reset_permanent_failures()


class TestFailureClassification:
    def test_rejected_credentials_are_permanent(self) -> None:
        assert llm.classify_failure(_status_error(401)) == "permanent"
        assert llm.classify_failure(_status_error(403)) == "permanent"

    def test_bad_requests_and_unknown_models_are_permanent(self) -> None:
        assert llm.classify_failure(_status_error(400)) == "permanent"
        assert llm.classify_failure(_status_error(404)) == "permanent"

    def test_overload_and_transport_errors_are_transient(self) -> None:
        assert llm.classify_failure(_status_error(429)) == "transient"
        assert llm.classify_failure(_status_error(503)) == "transient"
        assert llm.classify_failure(OSError("connection refused")) == "transient"
        assert llm.classify_failure(TimeoutError()) == "transient"

    def test_credential_exceptions_are_permanent(self) -> None:
        assert llm.classify_failure(llm.ClaudeCredentialError("no token")) == (
            "permanent"
        )
        assert llm.classify_failure(llm.LLMPermanentError("dead")) == "permanent"
        # The unavailability an unreachable local server raises is not.
        assert llm.classify_failure(llm.LLMUnavailableError("ollama down")) == (
            "transient"
        )

    async def test_attempt_kind_reaches_the_audit_event(self) -> None:
        first = _StubProvider("claude_code", error=_status_error(401))
        second = _StubProvider("ollama", text="local")

        with (
            _chain(first, second),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            result = await llm.agenerate("q")

        assert result.attempts[0].kind == "permanent"
        assert result.attempts[1].kind is None  # success
        assert log.call_args[0][1]["attempts"][0]["kind"] == "permanent"


class TestPermanentFailureMemory:
    async def test_a_rejected_key_is_skipped_on_the_next_call(self) -> None:
        """The point of the item: stop re-hitting a 401 on every request."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            result = await llm.agenerate("q again")

        assert claude.calls == 1  # not called the second time
        skipped = result.attempts[0]
        assert skipped.skipped_reason is not None
        assert skipped.skipped_reason.startswith("auth failed at ")

    async def test_a_transient_failure_is_not_remembered(self) -> None:
        claude = _StubProvider("claude_code", error=_status_error(503))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            await llm.agenerate("q again")

        assert claude.calls == 2  # an overloaded vendor is retried

    async def test_a_bad_request_does_not_poison_the_tier(self) -> None:
        """A 400 indicts one prompt, not the credential."""
        claude = _StubProvider("claude_code", error=_status_error(400))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            await llm.agenerate("q again")

        assert claude.calls == 2

    async def test_the_memory_expires(self, settings) -> None:
        settings.LLM_PERMANENT_FAILURE_TTL_S = 300.0
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            with patch("time.time", return_value=time.time() + 3600):
                await llm.agenerate("later")

        assert claude.calls == 2

    async def test_a_zero_ttl_disables_the_memory(self, settings) -> None:
        settings.LLM_PERMANENT_FAILURE_TTL_S = 0
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            await llm.agenerate("q again")

        assert claude.calls == 2

    async def test_warns_once_per_window(self, caplog) -> None:
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama), caplog.at_level("WARNING"):
            await llm.agenerate("q")
            await llm.agenerate("q again")

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "credential rejected" in warnings[0].getMessage()

    async def test_the_verdict_is_shared_across_processes(self) -> None:
        """BL-20260905-71: the memory is L1 + the Django cache, so a rejected
        key costs one call *per window*, not one per daphne/Celery process."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            # A fresh worker: empty in-process memory, same shared cache.
            router._permanent_failures.clear()
            result = await llm.agenerate("q again")

        assert claude.calls == 1  # the second worker never re-earned the 401
        skipped = result.attempts[0].skipped_reason
        assert skipped is not None and skipped.startswith("auth failed at ")

    async def test_a_shared_verdict_expires_on_its_original_timestamp(self) -> None:
        """Adopting late must not restart the window."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            router._permanent_failures.clear()
            with patch("time.time", return_value=time.time() + 3600):
                await llm.agenerate("later")

        assert claude.calls == 2

    async def test_a_broken_cache_backend_degrades_to_per_process_memory(
        self,
    ) -> None:
        """Fail-open: an unreachable cache must never break a model call."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        class _Broken:
            async def aget(self, key: str) -> Any:
                raise RuntimeError("cache down")

            async def aset(self, key: str, value: Any, timeout: float) -> None:
                raise RuntimeError("cache down")

        with _chain(claude, ollama), patch.object(router, "_shared_cache", _Broken):
            await llm.agenerate("q")
            result = await llm.agenerate("q again")
            router._permanent_failures.clear()
            third = await llm.agenerate("third")

        # L1 still works within the process...
        assert result.attempts[0].skipped_reason is not None
        # ...and without L2 a fresh process simply re-earns the 401 as before.
        assert third.text == "local"
        assert claude.calls == 2

    async def test_chain_status_surfaces_the_misconfiguration(self) -> None:
        """A rejected key is invisible to a reachability probe."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            await llm.agenerate("q")
            status = await llm.chain_status()

        entry = next(e for e in status if e["provider"] == "claude_code")
        assert "auth failed at " in entry["last_permanent_error"]
        assert "last_permanent_error" not in status[1]


class TestFailFastOnPermanent:
    async def test_flag_stops_the_chain_instead_of_downgrading(self, settings) -> None:
        settings.LLM_FAIL_FAST_ON_PERMANENT = True
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with (
            _chain(claude, ollama),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
            pytest.raises(llm.LLMPermanentError) as exc,
        ):
            await llm.agenerate("q")

        assert ollama.calls == 0
        assert "LLM_FAIL_FAST_ON_PERMANENT" in str(exc.value)
        # Still audited: a refused request is an event like any other.
        assert log.call_args[0][1]["ok"] is False

    async def test_fail_fast_error_is_still_an_llm_unavailable_error(
        self, settings
    ) -> None:
        """Existing callers catch the base class; they must keep working."""
        settings.LLM_FAIL_FAST_ON_PERMANENT = True
        claude = _StubProvider("claude_code", error=_status_error(401))

        with _chain(claude), pytest.raises(llm.LLMUnavailableError):
            await llm.agenerate("q")

    async def test_transient_failures_still_fall_through_under_the_flag(
        self, settings
    ) -> None:
        settings.LLM_FAIL_FAST_ON_PERMANENT = True
        claude = _StubProvider("claude_code", error=_status_error(503))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            result = await llm.agenerate("q")

        assert result.text == "local"

    async def test_default_still_reaches_the_local_tier(self) -> None:
        """Constitution §13: an honest local answer beats no answer."""
        claude = _StubProvider("claude_code", error=_status_error(401))
        ollama = _StubProvider("ollama", text="local")

        with _chain(claude, ollama):
            result = await llm.agenerate("q")

        assert result.provider == "ollama"


# ---------------------------------------------------------------------------
# Streaming (BL-20260811-20)
# ---------------------------------------------------------------------------


class _StreamProvider(_StubProvider):
    """A provider double that streams deltas, optionally failing part-way."""

    def __init__(
        self,
        name: str,
        *,
        deltas: tuple[str, ...] = ("a", "b"),
        fail_after: int | None = None,
        error: Exception | None = None,
        usage: LLMUsage | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._deltas = deltas
        self._fail_after = fail_after
        self._stream_error = error
        self._usage = usage
        self.streams = 0

    async def astream(self, request: LLMRequest) -> Any:
        self.streams += 1
        for index, delta in enumerate(self._deltas):
            if self._fail_after is not None and index == self._fail_after:
                raise self._stream_error or OSError("stream died")
            yield delta
        if self._fail_after == len(self._deltas):
            raise self._stream_error or OSError("stream died")
        yield ProviderReply("", self._usage)


async def _collect(stream: Any) -> list[Any]:
    return [chunk async for chunk in stream]


class TestStreaming:
    async def test_yields_deltas_tagged_with_the_serving_tier(self) -> None:
        provider = _StreamProvider("claude_code", deltas=("Mar", "bury"))

        with _chain(provider):
            chunks = await _collect(llm.astream("q"))

        assert [c.text for c in chunks] == ["Mar", "bury"]
        assert [c.provider for c in chunks] == ["claude_code", "claude_code"]
        assert chunks[0].model_label == "claude_code/claude_code-model"
        # The label has to arrive with the first delta, not at the end: a UI
        # rendering tokens can only attribute them honestly if it knows the
        # tier before the answer is complete.
        assert chunks[0].first is True
        assert chunks[1].first is False

    async def test_empty_usage_frame_is_not_yielded_to_the_caller(self) -> None:
        provider = _StreamProvider(
            "ollama", deltas=("x",), usage=LLMUsage(input_tokens=3, output_tokens=1)
        )

        with _chain(provider):
            chunks = await _collect(llm.astream("q"))

        assert [c.text for c in chunks] == ["x"]

    async def test_falls_back_when_a_tier_dies_before_the_first_token(self) -> None:
        first = _StreamProvider("claude_code", deltas=(), fail_after=0)
        second = _StreamProvider("ollama", deltas=("local",))

        with _chain(first, second):
            chunks = await _collect(llm.astream("q"))

        assert [c.text for c in chunks] == ["local"]
        assert second.streams == 1

    async def test_does_not_fall_back_once_a_token_was_emitted(self) -> None:
        """Splicing two tiers' answers together would be a fabrication."""
        first = _StreamProvider("claude_code", deltas=("half an ",), fail_after=1)
        second = _StreamProvider("ollama", deltas=("whole answer",))

        seen: list[str] = []
        with _chain(first, second), pytest.raises(llm.LLMStreamInterrupted) as caught:
            async for chunk in llm.astream("q"):
                seen.append(chunk.text)

        assert seen == ["half an "]
        assert caught.value.partial == "half an "
        assert second.streams == 0

    async def test_interruption_is_still_an_unavailable_error(self) -> None:
        """Existing `except LLMUnavailableError` handlers keep working."""
        provider = _StreamProvider("claude_code", deltas=("x",), fail_after=1)

        with _chain(provider), pytest.raises(llm.LLMUnavailableError):
            await _collect(llm.astream("q"))

    async def test_a_provider_without_astream_is_buffered_into_one_delta(self) -> None:
        provider = _StubProvider("ollama", text="whole reply")

        with _chain(provider):
            chunks = await _collect(llm.astream("q"))

        assert [c.text for c in chunks] == ["whole reply"]
        assert chunks[0].first is True

    async def test_unconfigured_tiers_are_skipped(self) -> None:
        first = _StreamProvider("claude_code", configured=False)
        second = _StreamProvider("ollama", deltas=("local",))

        with _chain(first, second):
            chunks = await _collect(llm.astream("q"))

        assert [c.provider for c in chunks] == ["ollama"]
        assert first.streams == 0

    async def test_empty_chain_raises_rather_than_yielding_nothing(self) -> None:
        provider = _StreamProvider("ollama", deltas=(), fail_after=0)

        with _chain(provider), pytest.raises(llm.LLMUnavailableError):
            await _collect(llm.astream("q"))

    async def test_restricting_providers_is_honoured(self) -> None:
        settings_chain = _StreamProvider("ollama", deltas=("local",))

        with patch(
            "law_ai.core.llm.router.build_chain", return_value=(settings_chain,)
        ) as build:
            await _collect(llm.astream("q", providers=("ollama",)))

        build.assert_called_once_with(("ollama",))


class TestStreamProvenance:
    async def test_success_writes_one_streamed_llm_call_event(self) -> None:
        provider = _StreamProvider(
            "claude_code",
            deltas=("ab", "cd"),
            usage=LLMUsage(input_tokens=11, output_tokens=2),
        )

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await _collect(llm.astream("q", agent="lsat_tutor"))

        log.assert_called_once()
        event_type, payload = log.call_args[0]
        assert event_type == "llm_call"
        assert payload["streamed"] is True
        assert payload["ok"] is True
        assert payload["agent"] == "lsat_tutor"
        assert payload["output_chars"] == 4  # the buffered text, not the deltas
        assert payload["input_tokens"] == 11

    async def test_buffered_calls_are_still_marked_unstreamed(self) -> None:
        provider = _StubProvider("claude_code", text="hi")

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await llm.agenerate("q")

        assert log.call_args[0][1]["streamed"] is False

    async def test_a_broken_stream_records_what_the_caller_already_saw(self) -> None:
        provider = _StreamProvider("claude_code", deltas=("partial",), fail_after=1)

        with (
            _chain(provider),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
            pytest.raises(llm.LLMStreamInterrupted),
        ):
            await _collect(llm.astream("q"))

        payload = log.call_args[0][1]
        assert payload["ok"] is False
        assert payload["streamed"] is True
        assert payload["partial_chars"] == len("partial")

    async def test_fallback_before_the_first_token_is_visible(self) -> None:
        first = _StreamProvider("claude_code", deltas=(), fail_after=0)
        second = _StreamProvider("ollama", deltas=("local",))

        with (
            _chain(first, second),
            patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        ):
            await _collect(llm.astream("q"))

        payload = log.call_args[0][1]
        assert payload["chain"] == ["claude_code", "ollama"]
        assert payload["fell_back"] is True
