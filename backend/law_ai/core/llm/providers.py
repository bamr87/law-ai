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

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from law_ai.core import claude_code, xai, xai_oauth
from law_ai.core.llm.base import (
    LLMPermanentError,
    LLMRequest,
    LLMUnavailableError,
)
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.usage import LLMUsage, ProviderReply

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

    def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Token deltas from the Messages API SSE feed (BL-20260811-20)."""
        return claude_code.astream(
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
            # reason and falls through to Ollama. Permanent, because no retry
            # and no other tier can mint a credential: the router remembers it
            # and stops re-asking for a TTL window (BL-20260811-23).
            raise LLMPermanentError(str(exc)) from exc

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Token deltas from xAI's SSE feed (BL-20260811-20).

        The auth translation :meth:`agenerate` performs applies here too: a
        dead credential is this tier being unavailable, not the request
        failing, so the router records a reason and moves on.
        """
        try:
            async for delta in xai.astream(
                request.prompt,
                system=request.system,
                model_id=self.model_for(request),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_schema=request.response_schema,
                json_mode=request.json_mode,
            ):
                yield delta
        except xai_oauth.XaiAuthError as exc:
            raise LLMPermanentError(str(exc)) from exc

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

    def model_candidates(self, request: LLMRequest) -> tuple[str, ...]:
        """The models to try, in order: the primary, then ``FALLBACK_MODEL``.

        Model fallback is the local tier's answer to the one failure waiting
        cannot fix: a 404 because the configured model was never pulled on
        this machine (BL-20260810-05). ``FALLBACK_MODEL`` names a smaller
        model the box is likelier to hold — the GPU overlay, for instance,
        serves ``llama3.1:70b-q4_K_M`` and falls back to the 7B Mistral. It is
        skipped when blank or identical to the primary, so a stock laptop
        config makes exactly one call.
        """
        primary = self.model_for(request)
        fallback = str(getattr(settings, "FALLBACK_MODEL", "") or "").strip()
        if not fallback or fallback == primary:
            return (primary,)
        return (primary, fallback)

    async def agenerate(self, request: LLMRequest) -> str:
        """Call Ollama, failing fast when the server is unreachable.

        The TTL-cached reachability probe keeps a down Ollama from burning the
        full request timeout at the tail of the chain. Once the server is
        known to be up, transient failures — a dropped connection, a read
        timeout while a model loads, a 429/5xx while it is busy — are retried
        by tenacity with bounded exponential backoff (constitution §8;
        ``OLLAMA_MAX_RETRIES`` total attempts, default 2;
        ``OLLAMA_REQUEST_TIMEOUT_S`` applies per attempt) so one hiccup on the
        local tier does not fail a whole agent run (BL-20260810-05). A 404
        means the model is not pulled: no retry, but the call falls back to
        ``FALLBACK_MODEL`` when that names a different model. Anything else (a
        400) raises on the first attempt.
        """
        from law_ai.agents_runtime import llm as llm_runtime

        if not await llm_runtime.ollama_available_async():
            raise LLMUnavailableError(
                f"Ollama unreachable at {settings.OLLAMA_BASE_URL}"
            )

        url = str(settings.OLLAMA_BASE_URL).rstrip("/") + "/api/generate"
        timeout = httpx.Timeout(float(settings.OLLAMA_REQUEST_TIMEOUT_S))
        candidates = self.model_candidates(request)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for index, model in enumerate(candidates):
                try:
                    return await self._generate_with_retries(
                        client, url, request, model
                    )
                except httpx.HTTPStatusError as exc:
                    last = index == len(candidates) - 1
                    if exc.response.status_code != _OLLAMA_MISSING_MODEL_STATUS or last:
                        raise
                    logger.warning(
                        "Ollama model %s is not pulled; falling back to %s",
                        model,
                        candidates[index + 1],
                    )
        # Unreachable: the loop either returns or raises on the last candidate.
        raise LLMUnavailableError("Ollama: exhausted retries without a response")

    async def _generate_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        request: LLMRequest,
        model: str,
    ) -> ProviderReply:
        """One model's ``/api/generate`` call, retried by tenacity."""
        payload = self._payload(request, stream=False, model=model)
        attempts = max(1, int(getattr(settings, "OLLAMA_MAX_RETRIES", 2)))
        retrying = AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(
                initial=_OLLAMA_BACKOFF_BASE_S,
                max=_OLLAMA_BACKOFF_CAP_S,
                jitter=_OLLAMA_BACKOFF_JITTER_S,
            ),
            retry=retry_if_exception(_ollama_retryable),
            sleep=_ollama_sleep,
            before_sleep=_log_ollama_retry,
            reraise=True,
        )
        return await retrying(self._generate_once, client, url, payload, model)

    async def _generate_once(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, Any],
        model: str,
    ) -> ProviderReply:
        """A single un-retried POST to ``/api/generate``."""
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return ProviderReply(
            str(data.get("response") or "").strip(),
            _ollama_usage(data),
            model=model,
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream ``/api/generate`` as NDJSON deltas (BL-20260811-20).

        Ollama streams newline-delimited JSON rather than SSE: one object per
        token carrying ``response``, and a final ``done`` object carrying the
        eval counts. The reachability gate still applies — a down local server
        must fail fast at the tail of the chain — but the retry loop
        :meth:`agenerate` uses does not: a retry after the first delta would
        replay tokens the caller already saw.
        """
        from law_ai.agents_runtime import llm as llm_runtime

        if not await llm_runtime.ollama_available_async():
            raise LLMUnavailableError(
                f"Ollama unreachable at {settings.OLLAMA_BASE_URL}"
            )

        url = str(settings.OLLAMA_BASE_URL).rstrip("/") + "/api/generate"
        payload = self._payload(request, stream=True)
        timeout = httpx.Timeout(float(settings.OLLAMA_REQUEST_TIMEOUT_S))
        usage: LLMUsage | None = None
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", url, json=payload) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                chunk = _ollama_line(line)
                if chunk is None:
                    continue
                text, done = chunk
                if done is not None:
                    usage = done
                if text:
                    yield text
        yield ProviderReply("", usage)

    def _payload(
        self, request: LLMRequest, *, stream: bool, model: str | None = None
    ) -> dict[str, Any]:
        """The ``/api/generate`` body shared by the buffered and streamed calls."""
        payload: dict[str, Any] = {
            "model": model or self.model_for(request),
            "prompt": _with_system(request),
            "stream": stream,
            "options": {"temperature": request.temperature},
        }
        # Ollama structured outputs: a JSON Schema in `format` when we have
        # one, else plain JSON mode. Anything else leaves `format` unset.
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        elif request.json_mode:
            payload["format"] = "json"
        return payload

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


# Transient Ollama statuses worth one more try: 429 (busy), 5xx (a model still
# loading, a crashed runner). A 404 means the model is not pulled and a 400
# means the request is wrong — neither improves with waiting.
_OLLAMA_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# "model not found": the one failure a *different model* can fix, so it drives
# the fallback-model hop rather than a retry (BL-20260810-05).
_OLLAMA_MISSING_MODEL_STATUS = 404

# Backoff is short on purpose: Ollama sits at the tail of the chain behind two
# hosted tiers, so a slow retry here lands on top of everything that already
# failed. Exponential from half a second, capped, with jitter so parallel
# workers do not re-hit a busy server in lockstep.
_OLLAMA_BACKOFF_BASE_S = 0.5
_OLLAMA_BACKOFF_CAP_S = 8.0
_OLLAMA_BACKOFF_JITTER_S = 0.25


def _ollama_usage(data: dict[str, Any]) -> LLMUsage | None:
    """Token counts from an ``/api/generate`` response.

    Ollama reports them at the top level as ``prompt_eval_count`` (input) and
    ``eval_count`` (output) rather than in a ``usage`` object. They cost
    nothing to serve, but recording them keeps the audit event's shape uniform
    across tiers (BL-20260811-21).
    """
    return LLMUsage.from_counts(data.get("prompt_eval_count"), data.get("eval_count"))


def _ollama_line(line: str) -> tuple[str, LLMUsage | None] | None:
    """Parse one NDJSON line into ``(text, usage-when-final)``.

    ``None`` for a blank or undecodable line: a stream must not die on a frame
    the client does not model. Split out of the provider so the grammar is
    unit-testable without a socket.
    """
    raw = line.strip()
    if not raw:
        return None
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    if event.get("error"):
        raise LLMUnavailableError(f"Ollama stream error: {str(event['error'])[:200]}")
    text = str(event.get("response") or "")
    usage = _ollama_usage(event) if event.get("done") else None
    return text, usage


def _ollama_retryable(exc: BaseException) -> bool:
    """True for the Ollama failures another attempt can plausibly fix.

    A dropped connection or a read timeout while a model loads
    (``httpx.TransportError``), and the busy/overloaded statuses in
    :data:`_OLLAMA_RETRYABLE_STATUS`. A 404 (model not pulled) and a 400 (bad
    request) are excluded on purpose: waiting changes neither.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _OLLAMA_RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


async def _ollama_sleep(seconds: float) -> None:
    """The wait tenacity performs between Ollama attempts.

    Indirection on purpose: tenacity resolves this once at construction, so
    routing it through the module-level ``asyncio`` keeps the sleep patchable
    from tests that must not actually wait.
    """
    await asyncio.sleep(seconds)


def _log_ollama_retry(state: RetryCallState) -> None:
    """Log the transient failure tenacity is about to sit out."""
    outcome = state.outcome
    exc = outcome.exception() if outcome is not None else None
    detail = type(exc).__name__ if exc is not None else "unknown"
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"HTTP {exc.response.status_code}"
    logger.info(
        "Ollama %s; retrying (attempt %s) in %.1fs",
        detail,
        state.attempt_number,
        state.next_action.sleep if state.next_action is not None else 0.0,
    )


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
