"""Tests for the xAI Grok transport and its chain tier (spec 050).

Covers the request shape, the failure contract the router depends on (a dead
credential is a *skipped tier*, not a failed request), and the structural
guarantee that the suite cannot reach xAI at all.
"""

from __future__ import annotations

import json
import time
from io import StringIO
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from django.core.management import call_command

from law_ai.core import xai, xai_oauth
from law_ai.core.llm import providers as llm_providers
from law_ai.core.llm.base import (
    LLMPermanentError,
    LLMRequest,
    LLMResult,
    LLMUnavailableError,
)
from law_ai.core.usage import LLMUsage, usage_of


@pytest.fixture
def authorised(tmp_path, settings) -> Any:
    """A live-looking credential so the transport gets past the auth gate."""
    settings.XAI_CREDENTIALS_PATH = str(tmp_path / "credentials.json")
    settings.XAI_ACCESS_TOKEN = ""
    settings.XAI_REFRESH_TOKEN = ""
    settings.XAI_BASE_URL = "https://api.x.ai/v1"
    xai_oauth.save_credentials(
        xai_oauth.Credentials(
            access="live-token", refresh="r", expires_at=time.time() + 3600
        )
    )
    return settings


def _mock_transport(handler: Any) -> Any:
    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    return patch("httpx.AsyncClient", _factory)


def _ok(content: str = "hello", finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"role": "assistant", "content": content},
                }
            ]
        },
    )


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


class TestRequestShape:
    async def test_bearer_token_and_endpoint(self, authorised) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return _ok()

        with _mock_transport(handler):
            assert await xai.generate("hi") == "hello"

        assert seen["url"] == "https://api.x.ai/v1/chat/completions"
        assert seen["auth"] == "Bearer live-token"

    async def test_system_prompt_becomes_a_system_message(self, authorised) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.read().decode()
            return _ok()

        with _mock_transport(handler):
            await xai.generate("hi", system="be terse")

        assert '"role": "system"' in seen["body"].replace(
            '"role":"system"', '"role": "system"'
        )

    async def test_schema_becomes_structured_output(self, authorised) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.read().decode()
            return _ok('{"a": 1}')

        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        with _mock_transport(handler):
            await xai.generate("hi", response_schema=schema)

        assert "json_schema" in seen["body"]

    async def test_json_mode_without_schema(self, authorised) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.read().decode()
            return _ok("{}")

        with _mock_transport(handler):
            await xai.generate("hi", json_mode=True)

        assert "json_object" in seen["body"]

    async def test_temperature_is_forwarded(self, authorised) -> None:
        """Unlike the Claude tiers, xAI accepts sampling params — don't drop them."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.read().decode()
            return _ok()

        with _mock_transport(handler):
            await xai.generate("hi", temperature=0.7)

        assert "0.7" in seen["body"]


# ---------------------------------------------------------------------------
# Failure contract
# ---------------------------------------------------------------------------


class TestFailures:
    async def test_content_filter_raises_rather_than_returning_blank(
        self, authorised
    ) -> None:
        """A filtered completion is a 200 with empty content (constitution §13)."""
        with (
            _mock_transport(lambda request: _ok("", finish="content_filter")),
            pytest.raises(xai.XaiRefusalError),
        ):
            await xai.generate("hi")

    async def test_truncation_raises(self, authorised) -> None:
        with (
            _mock_transport(lambda request: _ok("partial", finish="length")),
            pytest.raises(xai.XaiUnavailableError, match="truncated"),
        ):
            await xai.generate("hi")

    async def test_truncation_allowed_for_probes(self, authorised) -> None:
        with _mock_transport(lambda request: _ok("pong", finish="length")):
            assert await xai.generate("hi", allow_truncation=True) == "pong"

    async def test_401_refreshes_once_then_retries(self, authorised) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/oauth2/token"):
                calls.append("refresh")
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fresh",
                        "refresh_token": "r2",
                        "expires_in": 3600,
                    },
                )
            calls.append(request.headers.get("authorization", ""))
            if len(calls) == 1:
                return httpx.Response(401, json={"error": "expired"})
            return _ok("recovered")

        with _mock_transport(handler):
            assert await xai.generate("hi") == "recovered"

        assert "refresh" in calls
        assert calls[-1] == "Bearer fresh"

    async def test_403_is_not_retried(self, authorised) -> None:
        """xAI can 403 a paying subscriber; that is permanent for this deployment."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(403, json={"error": "not allowlisted"})

        with _mock_transport(handler), pytest.raises(httpx.HTTPStatusError):
            await xai.generate("hi")

        assert calls == 1

    async def test_read_timeout_is_not_retried(self, authorised) -> None:
        """Grok is slow; retrying a read timeout just burns another full one.

        Live measurement (2026-09-05): an IRAC analysis takes 56-103s. With the
        old 60s timeout and 3 retries, one slow call cost ~183s before the
        chain fell through and the analyst degraded to its offline fallback.
        """
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("too slow", request=request)

        with _mock_transport(handler), pytest.raises(httpx.ReadTimeout):
            await xai.generate("hi", max_retries=3)

        assert calls == 1

    async def test_connect_error_is_still_retried(self, authorised) -> None:
        """A genuine transient transport fault keeps its retries."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("boom", request=request)
            return _ok("recovered")

        with _mock_transport(handler):
            assert await xai.generate("hi", max_retries=3) == "recovered"

        assert calls == 2

    async def test_probe_reports_instead_of_raising(self, authorised) -> None:
        with _mock_transport(lambda request: httpx.Response(500, json={})):
            result = await xai.probe()
        assert result["reachable"] is False
        assert result["provider"] == "xai"


# ---------------------------------------------------------------------------
# Chain integration
# ---------------------------------------------------------------------------


class TestChainTier:
    def test_registered_between_anthropic_and_ollama(self) -> None:
        names = list(llm_providers.PROVIDER_REGISTRY)
        assert names.index("xai") > names.index("anthropic_api")
        assert names.index("xai") < names.index("ollama")

    async def test_dead_credential_is_a_skipped_tier_not_a_crash(
        self, tmp_path, settings
    ) -> None:
        """The router needs LLMUnavailableError to fall through to Ollama."""
        settings.XAI_CREDENTIALS_PATH = str(tmp_path / "missing.json")
        settings.XAI_ACCESS_TOKEN = ""
        settings.XAI_REFRESH_TOKEN = ""
        provider = llm_providers.XaiProvider()

        assert provider.configured() is False
        with pytest.raises(LLMUnavailableError):
            await provider.agenerate(LLMRequest(prompt="hi"))

    def test_model_override_wins(self, settings) -> None:
        settings.XAI_MODEL = "grok-4.6"
        provider = llm_providers.XaiProvider()
        request = LLMRequest(prompt="hi", models={"xai": "grok-build-0.1"})
        assert provider.model_for(request) == "grok-build-0.1"
        assert provider.model_for(LLMRequest(prompt="hi")) == "grok-4.6"


class TestSuiteCannotReachXai:
    """`make test` must never spend a subscription (spec 050 AC-5)."""

    def test_test_settings_leave_the_tier_unconfigured(self) -> None:
        from django.conf import settings as django_settings

        assert django_settings.XAI_ACCESS_TOKEN == ""
        assert django_settings.XAI_REFRESH_TOKEN == ""
        # A developer who has run `make xai-login` has a real credentials file;
        # the test settings must not be able to find it.
        assert not django_settings.XAI_CREDENTIALS_PATH.startswith(".xai")
        assert "127.0.0.1:1" in django_settings.XAI_BASE_URL
        assert "127.0.0.1:1" in django_settings.XAI_AUTH_BASE_URL


# ---------------------------------------------------------------------------
# Token usage (BL-20260811-21)
# ---------------------------------------------------------------------------


class TestUsageExtraction:
    """xAI's OpenAI-shaped ``usage`` block must reach the router."""

    async def test_generate_returns_the_reported_token_counts(self, authorised) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "hello"},
                        }
                    ],
                    "usage": {"prompt_tokens": 88, "completion_tokens": 9},
                },
            )

        with _mock_transport(handler):
            reply = await xai.generate("hi")

        assert reply == "hello"
        assert usage_of(reply) == LLMUsage(input_tokens=88, output_tokens=9)

    async def test_a_response_without_usage_is_not_an_error(self, authorised) -> None:
        with _mock_transport(lambda request: _ok()):
            reply = await xai.generate("hi")

        assert reply == "hello"
        assert usage_of(reply) is None


# ---------------------------------------------------------------------------
# Model discovery (BL-20260904-05)
# ---------------------------------------------------------------------------


def _models_response(*ids: str) -> httpx.Response:
    return httpx.Response(
        200, json={"data": [{"id": i, "object": "model"} for i in ids]}
    )


class TestListModels:
    async def test_returns_sorted_ids(self, authorised) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return _models_response("grok-4.6", "grok-3-mini", "grok-4.6")

        with _mock_transport(handler):
            models = await xai.list_models()

        assert models == ["grok-3-mini", "grok-4.6"]
        assert seen["url"] == "https://api.x.ai/v1/models"
        assert seen["auth"] == "Bearer live-token"

    async def test_a_malformed_listing_is_empty_not_an_error(self, authorised) -> None:
        with _mock_transport(lambda request: httpx.Response(200, json={"data": None})):
            assert await xai.list_models() == []

    async def test_http_errors_propagate(self, authorised) -> None:
        with (
            _mock_transport(lambda request: httpx.Response(403, json={})),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await xai.list_models()


class TestProbeNamesReachableModels:
    """A 404 on the configured id must say which ids *would* work."""

    async def test_404_completion_carries_available_models(self, authorised) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return _models_response("grok-3-mini", "grok-4-fast")
            return httpx.Response(404, json={"error": "model not found"})

        with _mock_transport(handler):
            probe = await xai.probe()

        assert probe["reachable"] is False
        assert "404" in probe["error"]
        assert probe["available_models"] == ["grok-3-mini", "grok-4-fast"]

    async def test_a_forbidden_listing_leaves_the_probe_intact(
        self, authorised
    ) -> None:
        """Some accounts have /v1/models outside their allowlist."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404 if "chat" in request.url.path else 403, json={})

        with _mock_transport(handler):
            probe = await xai.probe()

        assert probe["reachable"] is False
        assert "available_models" not in probe

    async def test_other_failures_do_not_list_models(self, authorised) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(500, json={})

        with _mock_transport(handler):
            probe = await xai.probe()

        assert probe["reachable"] is False
        assert "available_models" not in probe
        assert not [p for p in calls if p.endswith("/models")]


class TestValidateXaiCommand:
    """The operator command turns a 404 into an actionable model id."""

    def test_warns_when_the_configured_model_is_not_served(self, authorised) -> None:
        authorised.XAI_MODEL = "grok-9-imaginary"
        out = StringIO()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return _models_response("grok-4-fast", "grok-4.6")
            return _ok("pong")

        with _mock_transport(handler):
            call_command("validate_xai", "--skip-generate", stdout=out)

        printed = out.getvalue()
        assert "grok-9-imaginary is not in the list above" in printed
        assert "XAI_MODEL=grok-4-fast" in printed

    def test_no_warning_when_the_model_is_served(self, authorised) -> None:
        authorised.XAI_MODEL = "grok-4.6"
        out = StringIO()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return _models_response("grok-4.6")
            return _ok("pong")

        with _mock_transport(handler):
            call_command("validate_xai", "--skip-generate", stdout=out)

        assert "is not in the list above" not in out.getvalue()

    def test_an_unavailable_listing_does_not_stop_the_probe(self, authorised) -> None:
        out = StringIO()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(403, json={})
            return _ok("pong")

        with _mock_transport(handler):
            call_command("validate_xai", "--skip-generate", stdout=out)

        printed = out.getvalue()
        assert "listing         : unavailable" in printed
        assert "OAuth connection validated" in printed


# ---------------------------------------------------------------------------
# Interactive model override (BL-20260905-11)
# ---------------------------------------------------------------------------


class TestInteractiveModel:
    """A faster Grok for user-facing calls, without touching batch paths."""

    def test_blank_setting_is_a_no_op(self, settings) -> None:
        settings.XAI_MODEL = "grok-4.6"
        settings.XAI_INTERACTIVE_MODEL = ""
        assert xai.interactive_model() == "grok-4.6"
        assert xai.interactive_overrides() == {}

    def test_override_pins_only_the_xai_tier(self, settings) -> None:
        settings.XAI_MODEL = "grok-4.6"
        settings.XAI_INTERACTIVE_MODEL = "grok-4-fast"
        assert xai.interactive_model() == "grok-4-fast"
        assert xai.interactive_overrides() == {"xai": "grok-4-fast"}
        # Nothing else in the chain is renamed.
        assert set(xai.interactive_overrides()) == {llm_providers.XAI}

    def test_the_override_reaches_the_provider(self, settings) -> None:
        settings.XAI_INTERACTIVE_MODEL = "grok-4-fast"
        request = LLMRequest(prompt="q", models=xai.interactive_overrides())
        assert llm_providers.XaiProvider().model_for(request) == "grok-4-fast"

    async def test_the_tutor_sends_it(self, settings) -> None:
        """The interactive surface that most needs it actually passes it."""
        from law_ai.lsat.services import tutor as tutor_mod

        settings.XAI_INTERACTIVE_MODEL = "grok-4-fast"
        captured: dict[str, Any] = {}

        async def fake_agenerate(prompt: str, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return LLMResult(
                text="{}", provider="ollama", model="mistral", latency_ms=1.0
            )

        with patch.object(tutor_mod.llm, "agenerate", fake_agenerate):
            await tutor_mod._generate_coaching("prompt")

        assert captured["models"] == {"xai": "grok-4-fast"}

    async def test_the_tutor_sends_nothing_when_unset(self, settings) -> None:
        from law_ai.lsat.services import tutor as tutor_mod

        settings.XAI_INTERACTIVE_MODEL = ""
        captured: dict[str, Any] = {}

        async def fake_agenerate(prompt: str, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return LLMResult(
                text="{}", provider="ollama", model="mistral", latency_ms=1.0
            )

        with patch.object(tutor_mod.llm, "agenerate", fake_agenerate):
            await tutor_mod._generate_coaching("prompt")

        assert captured["models"] == {}

    async def test_the_authoring_path_sends_it(self, settings) -> None:
        """LSAT authoring measured 68s on this tier and was skipping the knob."""
        from law_ai.agents_runtime.crews import lsat_content_author

        settings.XAI_INTERACTIVE_MODEL = "grok-4-fast"
        captured: dict[str, Any] = {}

        async def fake_agenerate(prompt: str, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return LLMResult(
                text="{}", provider="ollama", model="mistral", latency_ms=1.0
            )

        with patch.object(lsat_content_author.llm, "agenerate", fake_agenerate):
            await lsat_content_author._generate("prompt")

        assert captured["models"] == {"xai": "grok-4-fast"}

    def test_no_user_facing_caller_is_left_out(self) -> None:
        """Every call a person waits on passes the override.

        Source-level on purpose: driving cross-check and the writing evaluator
        end to end needs a question bank and a graded essay, and the thing
        worth pinning is that none of these call sites silently loses the
        argument again (BL-20260905-11).
        """
        import inspect

        from law_ai.agents_runtime.crews.legal_analyst import LegalAnalyst
        from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
            LSATWritingEvaluator,
        )
        from law_ai.lsat.services.crosscheck import cross_check

        for func in (
            cross_check,
            LSATWritingEvaluator.run,
            LegalAnalyst._irac_text,
        ):
            assert "xai.interactive_overrides()" in inspect.getsource(func), func


# ---------------------------------------------------------------------------
# Streaming (BL-20260811-20)
# ---------------------------------------------------------------------------


def _sse(*frames: dict[str, Any]) -> httpx.Response:
    """An OpenAI-shaped SSE body, terminated the way xAI terminates one."""
    body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
    return httpx.Response(
        200,
        content=(body + "data: [DONE]\n\n").encode(),
        headers={"content-type": "text/event-stream"},
    )


def _delta(text: str, finish: str | None = None) -> dict[str, Any]:
    return {"choices": [{"delta": {"content": text}, "finish_reason": finish}]}


async def _drain(stream: Any) -> list[str]:
    return [chunk async for chunk in stream]


class TestAstream:
    async def test_yields_deltas_and_asks_for_usage(self, authorised) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _sse(
                _delta("Gro"),
                _delta("k", finish="stop"),
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 2}},
            )

        with _mock_transport(handler):
            chunks = await _drain(xai.astream("q"))

        assert [str(c) for c in chunks] == ["Gro", "k", ""]
        body = json.loads(seen[-1].content)
        assert body["stream"] is True
        # Without include_usage the terminal frame carries no counts and the
        # tier would bill invisibly.
        assert body["stream_options"] == {"include_usage": True}
        assert usage_of(chunks[-1]) == LLMUsage(input_tokens=9, output_tokens=2)

    async def test_content_filter_raises_instead_of_returning_blank(
        self, authorised
    ) -> None:
        with (
            _mock_transport(lambda request: _sse(_delta("", finish="content_filter"))),
            pytest.raises(xai.XaiRefusalError),
        ):
            await _drain(xai.astream("q"))

    async def test_truncation_raises_unless_allowed(self, authorised) -> None:
        with (
            _mock_transport(lambda request: _sse(_delta("half", finish="length"))),
            pytest.raises(xai.XaiUnavailableError),
        ):
            await _drain(xai.astream("q"))

    async def test_truncation_is_tolerated_when_the_caller_allows_it(
        self, authorised
    ) -> None:
        with _mock_transport(lambda request: _sse(_delta("half", finish="length"))):
            chunks = await _drain(xai.astream("q", allow_truncation=True))

        assert [str(c) for c in chunks] == ["half", ""]

    async def test_a_dead_credential_is_a_permanent_tier_failure(
        self, authorised, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The provider adapter translates it, exactly as agenerate does."""

        async def _boom(**kwargs: Any) -> str:
            raise xai_oauth.XaiAuthError("token revoked")

        monkeypatch.setattr(xai_oauth, "access_token", _boom)
        provider = llm_providers.XaiProvider()

        with pytest.raises(LLMPermanentError):
            await _drain(provider.astream(LLMRequest(prompt="q")))
