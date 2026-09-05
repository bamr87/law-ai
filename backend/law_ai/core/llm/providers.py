"""Concrete LLM transports for the provider chain (spec 034).

Three providers, in the order the default chain tries them:

1. :class:`ClaudeOAuthProvider` — Claude via a subscription OAuth token.
2. :class:`AnthropicAPIProvider` — Claude via ``ANTHROPIC_API_KEY``.
3. :class:`OllamaProvider` — the local open-weights model, last-resort fallback
   that keeps the product answering when both hosted paths are unreachable.

Each one is a thin adapter: the Anthropic pair delegate to
:mod:`law_ai.core.claude_code` (one transport, two auth modes) and the Ollama
one speaks ``/api/generate`` directly, matching the lightweight httpx client
the LSAT tutor has always used. Routing, fallback and provenance live in
:mod:`law_ai.core.llm.router` — providers only know how to make one call.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from law_ai.core import claude_code, xai, xai_oauth
from law_ai.core.llm.base import LLMRequest, LLMUnavailableError
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.core.llm.providers")

#: Provider names, also the tokens accepted in ``LLM_PROVIDER_CHAIN``.
CLAUDE_OAUTH = "claude_code"
ANTHROPIC_API = "anthropic_api"
XAI = "xai"
OLLAMA = "ollama"


class _AnthropicProvider:
    """Shared behaviour for the two Claude auth modes."""

    name = ""
    auth: claude_code.AuthMode = "oauth"

    def configured(self) -> bool:
        return claude_code.credential(self.auth) is not None

    def unconfigured_reason(self) -> str | None:
        if self.configured():
            return None
        return (
            "CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`)"
            if self.auth == "oauth"
            else "ANTHROPIC_API_KEY is not set"
        )

    def model_for(self, request: LLMRequest) -> str:
        return request.model_for(self.name) or claude_code.model()

    async def agenerate(self, request: LLMRequest) -> str:
        """One Messages API call; retries transient 429/5xx internally.

        ``request.temperature`` is deliberately **not** forwarded: sampling
        parameters were removed on current Claude models and now return a 400.
        Claude output is steered by the prompt and the ``effort`` level.
        """
        return await claude_code.generate(
            request.prompt,
            system=request.system,
            model_id=self.model_for(request),
            max_tokens=request.max_tokens,
            response_schema=request.response_schema,
            auth=self.auth,
        )

    async def probe(self) -> dict[str, Any]:
        return await claude_code.probe(auth=self.auth)


class ClaudeOAuthProvider(_AnthropicProvider):
    """Claude through a Claude subscription OAuth token (chain default)."""

    name = CLAUDE_OAUTH
    auth: claude_code.AuthMode = "oauth"


class AnthropicAPIProvider(_AnthropicProvider):
    """Claude through a standard ``ANTHROPIC_API_KEY``.

    Same models as the OAuth path — this tier exists so a deployment without a
    subscription token (CI, a server, a teammate's box) still gets Claude
    rather than dropping straight to the local model.
    """

    name = ANTHROPIC_API
    auth: claude_code.AuthMode = "api_key"

    def model_for(self, request: LLMRequest) -> str:
        override = request.model_for(self.name)
        if override:
            return override
        configured = str(getattr(settings, "ANTHROPIC_MODEL", "") or "").strip()
        return configured or claude_code.model()


class XaiProvider:
    """xAI Grok over a subscription OAuth token (chain tier 3, spec 050).

    Sits between the Anthropic tiers and the local model: a hosted fallback so
    an Anthropic outage costs a vendor rather than most of the answer quality.
    Sanctioned by constitution §1 as amended 2026-09-04 (ADR 0007).

    The credential lifecycle — device-code / loopback acquisition, rotation,
    cross-process refresh — lives in :mod:`law_ai.core.xai_oauth`; this adapter
    only knows how to make one call.
    """

    name = XAI

    def configured(self) -> bool:
        return xai_oauth.is_configured()

    def unconfigured_reason(self) -> str | None:
        return xai_oauth.unconfigured_reason()

    def model_for(self, request: LLMRequest) -> str:
        return request.model_for(self.name) or xai.model()

    async def agenerate(self, request: LLMRequest) -> str:
        """One chat-completions call.

        ``temperature`` **is** forwarded here, unlike the Claude tiers: those
        models removed sampling params and 400 on them, while xAI is
        OpenAI-compatible and honours the value the caller asked for.
        """
        try:
            return await xai.generate(
                request.prompt,
                system=request.system,
                model_id=self.model_for(request),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_schema=request.response_schema,
                json_mode=request.json_mode,
            )
        except xai_oauth.XaiAuthError as exc:
            # A dead or absent credential is this tier being unavailable, not
            # the request failing — surface it as such so the router records a
            # reason and falls through to Ollama.
            raise LLMUnavailableError(str(exc)) from exc

    async def probe(self) -> dict[str, Any]:
        return await xai.probe()


class OllamaProvider:
    """Local open-weights model via Ollama's ``/api/generate``.

    Last in the chain. Kept as a first-class provider (not a legacy path) so
    the product still answers — and still answers *locally* — when both hosted
    Claude tiers are unreachable, and so operators who need on-prem-only
    inference can pin the chain to this provider alone.
    """

    name = OLLAMA

    def configured(self) -> bool:
        return bool(str(getattr(settings, "OLLAMA_BASE_URL", "") or "").strip())

    def unconfigured_reason(self) -> str | None:
        return None if self.configured() else "OLLAMA_BASE_URL is not set"

    def model_for(self, request: LLMRequest) -> str:
        return request.model_for(self.name) or str(settings.OLLAMA_DEFAULT_MODEL)

    async def agenerate(self, request: LLMRequest) -> str:
        """Call Ollama, failing fast when the server is unreachable.

        The TTL-cached reachability probe keeps a down Ollama from burning the
        full request timeout at the tail of the chain.
        """
        from law_ai.agents_runtime import llm as llm_runtime

        if not await llm_runtime.ollama_available_async():
            raise LLMUnavailableError(
                f"Ollama unreachable at {settings.OLLAMA_BASE_URL}"
            )

        url = str(settings.OLLAMA_BASE_URL).rstrip("/") + "/api/generate"
        payload: dict[str, Any] = {
            "model": self.model_for(request),
            "prompt": _with_system(request),
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        # Ollama structured outputs: a JSON Schema in `format` when we have
        # one, else plain JSON mode. Anything else leaves `format` unset.
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        elif request.json_mode:
            payload["format"] = "json"

        timeout = httpx.Timeout(float(settings.OLLAMA_REQUEST_TIMEOUT_S))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return str(data.get("response") or "").strip()

    async def probe(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "provider": self.name,
            "model": str(settings.OLLAMA_DEFAULT_MODEL),
            "base_url": str(settings.OLLAMA_BASE_URL),
        }
        try:
            url = str(settings.OLLAMA_BASE_URL).rstrip("/") + "/api/tags"
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
            models = [m.get("name") for m in (resp.json().get("models") or [])]
            return {**base, "reachable": resp.status_code < 500, "models": models[:10]}
        except Exception as exc:  # pragma: no cover - defensive
            return {**base, "reachable": False, "error": str(exc)[:200]}


def _with_system(request: LLMRequest) -> str:
    """Fold the system instruction into the prompt for Ollama's raw endpoint."""
    if not request.system:
        return request.prompt
    return f"{request.system}\n\n{request.prompt}"


#: Every provider the chain knows how to build, keyed by its config token.
PROVIDER_REGISTRY: dict[str, type[Any]] = {
    CLAUDE_OAUTH: ClaudeOAuthProvider,
    ANTHROPIC_API: AnthropicAPIProvider,
    XAI: XaiProvider,
    OLLAMA: OllamaProvider,
}


__all__ = [
    "ANTHROPIC_API",
    "CLAUDE_OAUTH",
    "OLLAMA",
    "PROVIDER_REGISTRY",
    "XAI",
    "AnthropicAPIProvider",
    "ClaudeOAuthProvider",
    "OllamaProvider",
    "XaiProvider",
]
