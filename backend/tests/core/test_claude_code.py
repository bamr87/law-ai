"""Tests for the dev-time Claude Code OAuth provider (law_ai.core.claude_code).

Covers the constitution gate (dev-only, opt-in, token-present), the OAuth
Messages API request shape, and the health probe. No real network — the
Anthropic endpoint is mocked with respx.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from law_ai.core import claude_code

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _ok_response(text: str = "pong") -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


# ---------------------------------------------------------------------------
# Gating (the constitution lives here)
# ---------------------------------------------------------------------------


class TestGating:
    def test_default_is_inactive(self, settings) -> None:
        settings.LSAT_LLM_PROVIDER = "ollama"
        assert claude_code.is_selected() is False
        assert claude_code.is_active() is False

    def test_requires_dev_environment(self, settings) -> None:
        settings.LSAT_LLM_PROVIDER = "claude_code"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-test"
        settings.DEBUG = False
        settings.ENVIRONMENT = "production"
        assert claude_code.is_selected() is True
        assert claude_code.is_development() is False
        assert claude_code.is_active() is False
        assert "dev-time" in (claude_code.inactive_reason() or "")

    def test_requires_token(self, settings) -> None:
        settings.LSAT_LLM_PROVIDER = "claude_code"
        settings.DEBUG = True
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        assert claude_code.oauth_token() is None
        assert claude_code.is_active() is False
        assert "CLAUDE_CODE_OAUTH_TOKEN" in (claude_code.inactive_reason() or "")

    def test_active_when_all_conditions_met(self, settings) -> None:
        settings.LSAT_LLM_PROVIDER = "claude_code"
        settings.DEBUG = True
        settings.CLAUDE_CODE_OAUTH_TOKEN = "  sk-ant-oat01-test  "
        assert claude_code.oauth_token() == "sk-ant-oat01-test"
        assert claude_code.is_active() is True
        assert claude_code.inactive_reason() is None

    def test_development_via_environment_name(self, settings) -> None:
        settings.DEBUG = False
        settings.ENVIRONMENT = "development"
        assert claude_code.is_development() is True

    def test_model_label(self, settings) -> None:
        settings.CLAUDE_CODE_MODEL = "claude-opus-4-8"
        assert claude_code.model_label() == "claude_code/claude-opus-4-8"


# ---------------------------------------------------------------------------
# Messages API client (OAuth)
# ---------------------------------------------------------------------------


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
    async def test_disabled_outside_development(self, settings) -> None:
        settings.DEBUG = False
        settings.ENVIRONMENT = "production"
        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"
        result = await claude_code.probe()
        assert result["reachable"] is False
        assert "development" in result["reason"]

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
