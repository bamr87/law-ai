"""Tests for the xAI Grok transport and its chain tier (spec 050).

Covers the request shape, the failure contract the router depends on (a dead
credential is a *skipped tier*, not a failed request), and the structural
guarantee that the suite cannot reach xAI at all.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from law_ai.core import xai, xai_oauth
from law_ai.core.llm import providers as llm_providers
from law_ai.core.llm.base import LLMRequest, LLMUnavailableError


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
