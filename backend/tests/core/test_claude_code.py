"""Tests for the Anthropic Claude transport (law_ai.core.claude_code).

Covers credential resolution for both auth modes, the Messages API request
shape (OAuth bearer + beta header vs. x-api-key), refusal/truncation handling,
and the health probe. No real network — the endpoint is mocked with respx.

Note the dev-only gate these tests used to assert was repealed by constitution
§1's 2026-08-11 amendment (spec 034): Claude is now the default product
runtime, and provider selection lives in ``law_ai.core.llm.router``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from law_ai.core import claude_code
from law_ai.core.usage import LLMUsage, usage_of

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _ok_response(text: str = "pong") -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


# ---------------------------------------------------------------------------
# Gating (the constitution lives here)
# ---------------------------------------------------------------------------


class TestCredentials:
    def test_no_credentials_means_inactive(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = ""
        assert claude_code.oauth_token() is None
        assert claude_code.api_key() is None
        assert claude_code.is_active() is False
        assert "CLAUDE_CODE_OAUTH_TOKEN" in (claude_code.inactive_reason() or "")

    def test_oauth_token_is_stripped(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "  sk-ant-oat01-test  "
        assert claude_code.oauth_token() == "sk-ant-oat01-test"
        assert claude_code.is_active() is True
        assert claude_code.inactive_reason() is None

    def test_api_key_is_separate_from_oauth(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = "sk-ant-api03-test"
        assert claude_code.credential("oauth") is None
        assert claude_code.credential("api_key") == "sk-ant-api03-test"

    def test_production_no_longer_blocks_claude(self, settings) -> None:
        """The dev-only gate was repealed by the constitution §1 amendment."""
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        settings.DEBUG = False
        settings.ENVIRONMENT = "production"
        assert claude_code.is_development() is False
        # Previously this asserted is_active() is False.
        assert claude_code.is_active() is True

    def test_development_via_environment_name(self, settings) -> None:
        settings.DEBUG = False
        settings.ENVIRONMENT = "development"
        assert claude_code.is_development() is True

    def test_model_label(self, settings) -> None:
        settings.CLAUDE_CODE_MODEL = "claude-opus-5"
        assert claude_code.model_label() == "claude_code/claude-opus-5"

    def test_legacy_lsat_provider_pin_is_gone(self) -> None:
        """BL-20260811-22: ``LSAT_LLM_PROVIDER`` was folded into the chain.

        Guards against reintroduction — ``LLM_PROVIDER_CHAIN`` is the only
        selector, so neither the reader nor the setting may come back.
        """
        from django.conf import settings as django_settings

        assert not hasattr(claude_code, "is_selected")
        assert not hasattr(django_settings, "LSAT_LLM_PROVIDER")


class TestGenerate:
    @respx.mock
    async def test_builds_oauth_request(self, settings) -> None:
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        settings.CLAUDE_CODE_MODEL = "claude-opus-4-8"
        settings.CLAUDE_CODE_MAX_TOKENS = 1024
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response("hello"))

        out = await claude_code.generate("Explain choice B.", system="be terse")

        assert out == "hello"
        req = route.calls.last.request
        assert req.headers["authorization"] == "Bearer sk-ant-oat01-test"
        assert req.headers["anthropic-beta"] == "oauth-2025-04-20"
        assert req.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(req.content)
        assert body["model"] == "claude-opus-4-8"
        # The Claude Code identity must be the first system block for OAuth tokens.
        assert body["system"][0]["text"] == claude_code.CLAUDE_CODE_IDENTITY
        assert body["system"][1]["text"] == "be terse"
        assert body["messages"][0]["content"] == "Explain choice B."

    async def test_raises_without_token(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        with pytest.raises(claude_code.ClaudeCodeUnavailableError):
            await claude_code.generate("hi")

    @respx.mock
    async def test_concatenates_text_blocks(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "foo"},
                        {"type": "thinking", "thinking": "ignored"},
                        {"type": "text", "text": "bar"},
                    ]
                },
            )
        )
        assert await claude_code.generate("x") == "foobar"

    @respx.mock
    async def test_propagates_http_error(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(return_value=httpx.Response(401, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            await claude_code.generate("x")

    @respx.mock
    async def test_passes_response_schema_as_structured_output(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response('{"x":1}'))
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        }
        await claude_code.generate("hi", response_schema=schema)
        body = json.loads(route.calls.last.request.content)
        assert body["output_config"]["format"]["type"] == "json_schema"
        assert body["output_config"]["format"]["schema"] == schema

    @respx.mock
    async def test_omits_output_config_without_schema(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response("hi"))
        await claude_code.generate("hi")
        assert "output_config" not in json.loads(route.calls.last.request.content)

    @respx.mock
    async def test_retries_on_overloaded_then_succeeds(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        settings.CLAUDE_CODE_MAX_RETRIES = 3
        monkeypatch.setattr(claude_code.asyncio, "sleep", AsyncMock())  # no real wait
        route = respx.post(_MESSAGES_URL).mock(
            side_effect=[
                httpx.Response(529, json={"error": {"type": "overloaded_error"}}),
                _ok_response("recovered"),
            ]
        )
        out = await claude_code.generate("x")
        assert out == "recovered"
        assert route.call_count == 2

    @respx.mock
    async def test_raises_after_exhausting_retries(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        settings.CLAUDE_CODE_MAX_RETRIES = 2
        monkeypatch.setattr(claude_code.asyncio, "sleep", AsyncMock())
        respx.post(_MESSAGES_URL).mock(return_value=httpx.Response(529, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            await claude_code.generate("x")

    @respx.mock
    async def test_does_not_retry_client_error(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        settings.CLAUDE_CODE_MAX_RETRIES = 3
        monkeypatch.setattr(claude_code.asyncio, "sleep", AsyncMock())
        route = respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(400, json={})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await claude_code.generate("x")
        assert route.call_count == 1  # 400 is not retryable


class TestApiKeyAuth:
    """The second chain tier: same API, different credential."""

    @respx.mock
    async def test_uses_x_api_key_header_and_no_identity_block(self, settings) -> None:
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.ANTHROPIC_API_KEY = "sk-ant-api03-test"
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response("hi"))

        out = await claude_code.generate("q", system="be terse", auth="api_key")

        assert out == "hi"
        req = route.calls.last.request
        assert req.headers["x-api-key"] == "sk-ant-api03-test"
        # An API-key request is an ordinary API call: no bearer, no beta
        # header, and it must not claim to be the Claude Code CLI.
        assert "authorization" not in req.headers
        assert "anthropic-beta" not in req.headers
        body = json.loads(req.content)
        assert body["system"] == [{"type": "text", "text": "be terse"}]

    async def test_raises_without_api_key(self, settings) -> None:
        settings.ANTHROPIC_API_KEY = ""
        with pytest.raises(
            claude_code.ClaudeCodeUnavailableError, match="ANTHROPIC_API_KEY"
        ):
            await claude_code.generate("q", auth="api_key")


class TestSamplingParamsAreNotSent:
    @respx.mock
    async def test_payload_never_carries_temperature(self, settings) -> None:
        """`temperature`/`top_p`/`top_k` were removed on current Claude models.

        Sending any of them is a 400, so the transport must not emit them.
        """
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response())

        await claude_code.generate("q")

        body = json.loads(route.calls.last.request.content)
        assert "temperature" not in body
        assert "top_p" not in body
        assert "top_k" not in body


class TestEffort:
    @respx.mock
    async def test_effort_setting_lands_in_output_config(self, settings) -> None:
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        settings.CLAUDE_EFFORT = "high"
        route = respx.post(_MESSAGES_URL).mock(return_value=_ok_response())

        await claude_code.generate("q")

        body = json.loads(route.calls.last.request.content)
        assert body["output_config"]["effort"] == "high"


class TestStopReasons:
    """A refusal or a truncation must never look like a real answer."""

    @respx.mock
    async def test_refusal_raises_instead_of_returning_empty(self, settings) -> None:
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [],
                    "stop_reason": "refusal",
                    "stop_details": {"type": "refusal", "category": "cyber"},
                },
            )
        )

        with pytest.raises(claude_code.ClaudeRefusalError) as exc:
            await claude_code.generate("q")
        assert exc.value.category == "cyber"

    @respx.mock
    async def test_truncated_response_raises(self, settings) -> None:
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": '{"partial": '}],
                    "stop_reason": "max_tokens",
                },
            )
        )

        with pytest.raises(claude_code.ClaudeCodeUnavailableError, match="max_tokens"):
            await claude_code.generate("q")


class TestLoadsFirstJson:
    def test_plain_object(self) -> None:
        assert claude_code.loads_first_json('{"a": 1}') == {"a": 1}

    def test_ignores_trailing_prose(self) -> None:
        # Opus sometimes appends commentary after the JSON ("Extra data").
        assert claude_code.loads_first_json('{"a": 1}\n\nI notice the schema…') == {
            "a": 1
        }

    def test_skips_leading_prose_with_stray_brace(self) -> None:
        text = 'Here is the result for {section}:\n{"a": 1, "b": [1, 2]}'
        assert claude_code.loads_first_json(text) == {"a": 1, "b": [1, 2]}

    def test_strips_code_fence(self) -> None:
        assert claude_code.loads_first_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_raises_when_no_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            claude_code.loads_first_json("no json here at all")


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


class TestProbe:
    @respx.mock
    async def test_probes_in_production_now_that_the_gate_is_repealed(
        self, settings
    ) -> None:
        """Previously this asserted a hard refusal outside development."""
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.DEBUG = False
        settings.ENVIRONMENT = "production"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(return_value=_ok_response("pong"))

        result = await claude_code.probe()

        assert result["reachable"] is True
        assert result["development"] is False

    @respx.mock
    async def test_probe_treats_truncation_as_success(self, settings) -> None:
        """Thinking counts against max_tokens, so a probe stops at the cap.

        Regression guard: a strict truncation check here would report Claude
        permanently unreachable on every health poll.
        """
        settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "po"}],
                    "stop_reason": "max_tokens",
                },
            )
        )

        result = await claude_code.probe()

        assert result["reachable"] is True

    async def test_api_key_tier_reports_its_own_credential(self, settings) -> None:
        settings.ANTHROPIC_API_KEY = ""
        result = await claude_code.probe(auth="api_key")
        assert result["reachable"] is False
        assert result["provider"] == "anthropic_api"
        assert "ANTHROPIC_API_KEY" in result["reason"]

    async def test_missing_token(self, settings) -> None:
        settings.DEBUG = True
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        result = await claude_code.probe()
        assert result["reachable"] is False
        assert "CLAUDE_CODE_OAUTH_TOKEN" in result["reason"]

    @respx.mock
    async def test_reachable(self, settings) -> None:
        settings.DEBUG = True
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(return_value=_ok_response("pong"))
        result = await claude_code.probe()
        assert result["reachable"] is True
        assert result["sample"] == "pong"
        assert result["provider"] == "claude_code"

    @respx.mock
    async def test_unreachable_reports_error(self, settings) -> None:
        settings.DEBUG = True
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(return_value=httpx.Response(401, json={}))
        result = await claude_code.probe()
        assert result["reachable"] is False
        assert "401" in result["error"]


# ---------------------------------------------------------------------------
# Token usage (BL-20260811-21)
# ---------------------------------------------------------------------------


class TestUsageExtraction:
    """The Messages API ``usage`` block must reach the router."""

    @respx.mock
    async def test_generate_returns_the_reported_token_counts(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "hi"}],
                    "usage": {"input_tokens": 321, "output_tokens": 12},
                },
            )
        )

        reply = await claude_code.generate("q")

        assert reply == "hi"  # still a plain string to every caller
        assert usage_of(reply) == LLMUsage(input_tokens=321, output_tokens=12)

    @respx.mock
    async def test_a_response_without_usage_is_not_an_error(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(return_value=_ok_response("hi"))

        reply = await claude_code.generate("q")

        assert reply == "hi"
        assert usage_of(reply) is None

    @respx.mock
    async def test_a_malformed_usage_block_is_ignored(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "hi"}],
                    "usage": {"input_tokens": "lots", "output_tokens": None},
                },
            )
        )

        assert usage_of(await claude_code.generate("q")) is None


# ---------------------------------------------------------------------------
# Streaming (BL-20260811-20)
# ---------------------------------------------------------------------------


def _sse(*events: dict) -> httpx.Response:
    """A Messages API SSE body, framed the way Anthropic frames it."""
    lines: list[str] = []
    for event in events:
        lines.append(f"event: {event['type']}")
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    return httpx.Response(
        200,
        content="\n".join(lines).encode(),
        headers={"content-type": "text/event-stream"},
    )


def _text_delta(text: str) -> dict:
    return {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": text},
    }


async def _drain(stream) -> list[str]:
    return [chunk async for chunk in stream]


class TestAstream:
    @respx.mock
    async def test_yields_text_deltas_and_final_usage(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        route = respx.post(_MESSAGES_URL).mock(
            return_value=_sse(
                {"type": "message_start", "message": {"usage": {"input_tokens": 12}}},
                {"type": "content_block_start", "index": 0},
                _text_delta("Mar"),
                _text_delta("bury"),
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 5},
                },
                {"type": "message_stop"},
            )
        )

        chunks = await _drain(claude_code.astream("q"))

        assert [str(c) for c in chunks] == ["Mar", "bury", ""]
        assert json.loads(route.calls.last.request.content)["stream"] is True
        # The trailing empty delta is how the transport hands the router the
        # token counts without changing the `-> AsyncIterator[str]` contract.
        assert usage_of(chunks[-1]) == LLMUsage(input_tokens=12, output_tokens=5)

    @respx.mock
    async def test_ignores_thinking_blocks_and_keepalives(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=_sse(
                {"type": "ping"},
                {
                    "type": "content_block_delta",
                    "delta": {"type": "thinking_delta", "thinking": "hmm"},
                },
                _text_delta("answer"),
            )
        )

        chunks = await _drain(claude_code.astream("q"))

        assert [str(c) for c in chunks] == ["answer", ""]

    @respx.mock
    async def test_a_refusal_raises_rather_than_returning_the_partial(
        self, settings
    ) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=_sse(
                _text_delta("I can"),
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": "refusal",
                        "stop_details": {"category": "policy"},
                    },
                },
            )
        )

        with pytest.raises(claude_code.ClaudeRefusalError):
            await _drain(claude_code.astream("q"))

    @respx.mock
    async def test_truncation_raises_unless_allowed(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        body = _sse(
            _text_delta("half"),
            {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}},
        )
        respx.post(_MESSAGES_URL).mock(return_value=body)

        with pytest.raises(claude_code.ClaudeCodeUnavailableError):
            await _drain(claude_code.astream("q"))

    @respx.mock
    async def test_a_stream_error_frame_raises(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        respx.post(_MESSAGES_URL).mock(
            return_value=_sse(
                _text_delta("x"),
                {"type": "error", "error": {"message": "overloaded"}},
            )
        )

        with pytest.raises(claude_code.ClaudeCodeUnavailableError, match="overloaded"):
            await _drain(claude_code.astream("q"))

    async def test_raises_without_a_credential(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        with pytest.raises(claude_code.ClaudeCredentialError):
            await _drain(claude_code.astream("q"))

    @respx.mock
    async def test_api_key_mode_sends_the_api_key_header(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = "sk-ant-api03-x"
        route = respx.post(_MESSAGES_URL).mock(return_value=_sse(_text_delta("hi")))

        await _drain(claude_code.astream("q", auth="api_key"))

        assert route.calls.last.request.headers["x-api-key"] == "sk-ant-api03-x"
        assert "authorization" not in route.calls.last.request.headers
