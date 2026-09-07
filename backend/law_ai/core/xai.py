"""xAI Grok transport — chain tier 3 (spec 050).

Speaks the OpenAI-compatible ``/chat/completions`` surface at
``https://api.x.ai/v1`` with a subscription OAuth bearer token minted by
:mod:`law_ai.core.xai_oauth`. Structurally the sibling of
:mod:`law_ai.core.claude_code`: raw ``httpx`` (no SDK), transient-error
retries, and a near-free probe for the dashboard — so the two hosted tiers
fail and report the same way.

Constitution note (docs/constitution.md §1, amended 2026-09-04): xAI sits
between the Anthropic tiers and local Ollama. Provider selection, fallback and
the ``llm_call`` provenance event all live in :mod:`law_ai.core.llm.router`;
nothing here decides whether it is this tier's turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from law_ai.core import sse, xai_oauth
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.usage import LLMUsage, ProviderReply

logger = logging.getLogger("law_ai.core.xai")

PROVIDER_NAME = "xai"

#: Two output tokens is enough to prove the round-trip without spending real
#: subscription budget on dashboard polls.
_PROBE_MAX_TOKENS = 8

#: Transient statuses worth retrying with backoff. 403 is deliberately absent:
#: xAI enforces its own allowlist on the OAuth API surface and can 403 a paying
#: subscriber, which is a permanent condition for this deployment and should
#: fall through to the next tier immediately (spec 050 NFR-COMPAT-1).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})


class XaiUnavailableError(RuntimeError):
    """Raised when an xAI call cannot be completed with the current config."""


class XaiRefusalError(RuntimeError):
    """Raised when xAI's content filter declines the request.

    A filtered completion is a **successful HTTP 200** carrying
    ``finish_reason: "content_filter"`` and empty content; returning it
    unconditionally would hand the caller a silently blank answer. Raising lets
    the chain fall through and the caller degrade to an honest refusal
    (constitution §13).
    """


def model() -> str:
    """The configured Grok model id."""
    return str(getattr(settings, "XAI_MODEL", "grok-4.6") or "grok-4.6")


def interactive_model() -> str:
    """The Grok id to use on user-facing calls; ``XAI_MODEL`` when unset.

    Live measurement put xAI at 5-10x the Claude tiers on this product's work
    (IRAC 56-103s, LSAT authoring 68s), which is why ``XAI_REQUEST_TIMEOUT_S``
    is 240s. That is fine for a batch fallback and poor for anyone waiting at a
    keyboard, so interactive callers can pin a faster variant without touching
    the factory, eval, or autonomy paths (BL-20260905-11). Default blank — the
    right id has to be chosen against a real subscription, and picking one in
    code would silently change the fallback tier's answer quality for everyone.
    """
    override = str(getattr(settings, "XAI_INTERACTIVE_MODEL", "") or "").strip()
    return override or model()


def interactive_overrides() -> dict[str, str]:
    """``models=`` mapping for an interactive call — empty when unconfigured.

    Spread into :func:`law_ai.core.llm.agenerate` so a blank setting is a
    literal no-op and every other tier keeps its own configured model.
    """
    chosen = interactive_model()
    return {PROVIDER_NAME: chosen} if chosen != model() else {}


def model_label() -> str:
    """Audit-friendly identifier recorded as the producing model."""
    return f"{PROVIDER_NAME}/{model()}"


def base_url() -> str:
    return str(getattr(settings, "XAI_BASE_URL", "https://api.x.ai/v1")).rstrip("/")


def _completions_url() -> str:
    return f"{base_url()}/chat/completions"


def _models_url() -> str:
    return f"{base_url()}/models"


async def list_models() -> list[str]:
    """The model ids this subscription can actually reach, sorted.

    ``XAI_MODEL`` defaults to a hard-coded id, so an operator whose plan does
    not expose it gets a 404 on every request with nothing naming what *would*
    work (BL-20260904-05). Raises like any other transport call — callers that
    only want a hint (the probe) swallow the failure.
    """
    token = await xai_oauth.access_token()
    timeout = httpx.Timeout(float(getattr(settings, "XAI_REQUEST_TIMEOUT_S", 60.0)))
    headers = {
        "authorization": f"Bearer {token}",
        "user-agent": "law-ai",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(_models_url(), headers=headers)
        resp.raise_for_status()
        data = resp.json()
    entries = data.get("data") if isinstance(data, dict) else None
    ids = {
        str(entry["id"])
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("id")
    }
    return sorted(ids)


def _build_payload(
    prompt: str,
    *,
    system: str | None,
    model_id: str | None,
    max_tokens: int | None,
    temperature: float | None,
    response_schema: dict[str, Any] | None,
    json_mode: bool,
) -> dict[str, Any]:
    """Assemble the chat-completions body."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model_id or model(),
        "messages": messages,
        "max_tokens": max_tokens or int(getattr(settings, "XAI_MAX_TOKENS", 8192)),
        "stream": False,
    }
    # Unlike the Claude tiers — where sampling params were removed and now 400 —
    # xAI is OpenAI-compatible and honours temperature, so a caller that asked
    # for one gets it rather than having it silently dropped.
    if temperature is not None:
        payload["temperature"] = temperature
    # Structured outputs when the caller supplied a schema, plain JSON mode when
    # they only asked for JSON. Mirrors what the Ollama provider does with
    # `format`, so a caller gets the same guarantee whichever tier serves it.
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": response_schema,
            },
        }
    elif json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _extract_text(data: dict[str, Any], *, allow_truncation: bool = False) -> str:
    """Pull the assistant message out of a completions response.

    Guards ``finish_reason`` first: a content-filter stop carries empty content
    and must not read as an answer, and a ``length`` stop means the payload is
    truncated — for a schema-constrained call that is a broken JSON document,
    so both raise rather than returning something misleading.
    """
    choices = data.get("choices") or []
    if not choices:
        raise XaiUnavailableError("xAI response carried no choices")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    finish_reason = choice.get("finish_reason")
    if finish_reason == "content_filter":
        raise XaiRefusalError("xAI declined the request (content_filter)")

    message = choice.get("message") or {}
    text = str(message.get("content") or "").strip()

    if finish_reason == "length" and not allow_truncation:
        raise XaiUnavailableError(
            f"response truncated at max_tokens ({len(text)} chars) — raise XAI_MAX_TOKENS"
        )
    return text


def _extract_usage(data: dict[str, Any]) -> LLMUsage | None:
    """Read the OpenAI-compatible ``usage`` block into neutral token counts.

    xAI names them ``prompt_tokens``/``completion_tokens``; a missing or
    malformed block yields ``None`` so accounting never fails a good call
    (BL-20260811-21).
    """
    return LLMUsage.from_payload(
        data.get("usage"),
        input_key="prompt_tokens",
        output_key="completion_tokens",
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_schema: dict[str, Any] | None = None,
    json_mode: bool = False,
    max_retries: int | None = None,
    allow_truncation: bool = False,
) -> str:
    """Call xAI's chat-completions API and return the text reply.

    The return value is a :class:`~law_ai.core.usage.ProviderReply` — a ``str``
    carrying the response's token usage alongside the text, so per-tier spend
    is attributable in the audit log.

    Transient errors (429/5xx) retry with exponential backoff honouring
    ``retry-after``. A 401 gets exactly one forced token refresh and one retry —
    the access token may simply have aged out mid-flight — after which the error
    propagates so the router can fall through to the next tier.
    """
    payload = _build_payload(
        prompt,
        system=system,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        response_schema=response_schema,
        json_mode=json_mode,
    )
    timeout = httpx.Timeout(float(getattr(settings, "XAI_REQUEST_TIMEOUT_S", 60.0)))
    attempts = max(
        1,
        (
            max_retries
            if max_retries is not None
            else int(getattr(settings, "XAI_MAX_RETRIES", 3))
        ),
    )
    url = _completions_url()
    # Set to the token a 401 rejected, so the next access_token() refreshes past
    # a credential the stored deadline still considers valid.
    stale_access: str | None = None
    refreshed_once = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            token = await xai_oauth.access_token(stale_access=stale_access)
            stale_access = None
            headers = {
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "user-agent": "law-ai",
            }
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return ProviderReply(
                    _extract_text(data, allow_truncation=allow_truncation),
                    _extract_usage(data),
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 401 and not refreshed_once and attempt < attempts - 1:
                    # The token aged out mid-flight. Force one refresh and retry
                    # immediately; a second 401 means the credential is dead.
                    refreshed_once = True
                    stale_access = token
                    logger.info(
                        "xAI returned 401; forcing a token refresh and retrying"
                    )
                    continue
                if status not in _RETRYABLE_STATUS or attempt == attempts - 1:
                    raise
                wait = _retry_after_seconds(exc.response) or float(2**attempt)
                logger.info(
                    "xAI HTTP %s; retry %s/%s in %.1fs",
                    status,
                    attempt + 1,
                    attempts,
                    wait,
                )
                await asyncio.sleep(wait)
            except (httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                # A read timeout means xAI accepted the request and is still
                # thinking — Grok is a reasoning model and a long analysis can
                # genuinely outlast the deadline. Retrying replays identical
                # slow work and burns another full timeout, so a 3-attempt
                # default turns one slow call into ~3x the wait before the
                # chain falls through. Fail fast instead and let the router
                # reach the next tier; raise XAI_REQUEST_TIMEOUT_S if legitimate
                # calls are being cut off.
                logger.info(
                    "xAI %s after %.0fs; not retrying (raise XAI_REQUEST_TIMEOUT_S)",
                    type(exc).__name__,
                    float(getattr(settings, "XAI_REQUEST_TIMEOUT_S", 240.0)),
                )
                raise
            except httpx.TransportError as exc:
                if attempt == attempts - 1:
                    raise
                logger.info(
                    "xAI transport error (%s); retry %s/%s",
                    type(exc).__name__,
                    attempt + 1,
                    attempts,
                )
                await asyncio.sleep(float(2**attempt))
    # Unreachable: the loop either returns or raises on the final attempt.
    raise XaiUnavailableError("exhausted retries without a response")


@dataclass
class _StreamState:
    """Mutable accounting for one SSE feed (finish reason, usage, size)."""

    finish_reason: str | None = None
    input_tokens: Any = None
    output_tokens: Any = None
    chars: int = 0


def _sse_deltas(line: str, state: _StreamState) -> list[str]:
    """Text deltas carried by one ``data:`` line, updating *state* in place.

    Split out so the OpenAI-compatible event grammar is unit-testable without
    a socket. Unknown frames are ignored rather than raising: xAI is free to
    add fields, and a stream must not die on one it does not model.
    """
    event = sse.data_payload(line)
    if event is None:
        return []

    usage = event.get("usage")
    if isinstance(usage, dict):
        state.input_tokens = usage.get("prompt_tokens", state.input_tokens)
        state.output_tokens = usage.get("completion_tokens", state.output_tokens)

    choices = event.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return []  # the usage-only frame `include_usage` appends carries none
    choice = choices[0]
    if choice.get("finish_reason"):
        state.finish_reason = str(choice["finish_reason"])
    text = str((choice.get("delta") or {}).get("content") or "")
    if not text:
        return []
    state.chars += len(text)
    return [text]


async def astream(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_schema: dict[str, Any] | None = None,
    json_mode: bool = False,
    allow_truncation: bool = False,
) -> AsyncIterator[str]:
    """Stream a chat completion as text deltas (BL-20260811-20).

    Same body as :func:`generate` with ``stream: true`` and
    ``stream_options.include_usage``, so the terminal frame still carries the
    token counts the ``llm_call`` event bills the tier for.

    Not retried, and the 401-refresh dance :func:`generate` performs is
    skipped: a token that dies mid-stream cannot be recovered without
    replaying tokens the caller already rendered. A pre-stream 401 propagates
    so the router falls through to the next tier.
    """
    payload = _build_payload(
        prompt,
        system=system,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        response_schema=response_schema,
        json_mode=json_mode,
    )
    payload["stream"] = True
    payload["stream_options"] = {"include_usage": True}

    token = await xai_oauth.access_token()
    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "accept": "text/event-stream",
        "user-agent": "law-ai",
    }
    timeout = httpx.Timeout(float(getattr(settings, "XAI_REQUEST_TIMEOUT_S", 60.0)))

    state = _StreamState()
    async with (
        httpx.AsyncClient(timeout=timeout) as client,
        client.stream(
            "POST", _completions_url(), json=payload, headers=headers
        ) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            for delta in _sse_deltas(line, state):
                yield delta

    if state.finish_reason == "content_filter":
        raise XaiRefusalError("xAI declined the request (content_filter)")
    if state.finish_reason == "length" and not allow_truncation:
        raise XaiUnavailableError(
            f"streamed response truncated at max_tokens ({state.chars} chars) "
            "— raise XAI_MAX_TOKENS"
        )
    yield ProviderReply(
        "", LLMUsage.from_counts(state.input_tokens, state.output_tokens)
    )


async def _available_models_quietly() -> list[str] | None:
    """:func:`list_models` for diagnostics: never raises, ``None`` on failure."""
    try:
        return await list_models()
    except Exception:  # pragma: no cover - diagnostics must not mask the 404
        logger.debug("xAI model listing unavailable", exc_info=True)
        return None


async def probe() -> dict[str, Any]:
    """Reachability probe for the local-ai health endpoint.

    Never raises — a dead tier is reported inline so one bad provider cannot
    fail the whole health response.
    """
    base: dict[str, Any] = {
        "provider": PROVIDER_NAME,
        "auth": "oauth",
        "credential_present": xai_oauth.is_configured(),
        "model": model(),
        "base_url": base_url(),
    }
    if not base["credential_present"]:
        return {
            **base,
            "reachable": False,
            "reason": xai_oauth.unconfigured_reason() or "no xAI credentials",
        }
    try:
        sample = await generate(
            "Reply with the single word: pong",
            system="You are a connectivity probe. Reply with exactly one word.",
            max_tokens=_PROBE_MAX_TOKENS,
            max_retries=1,  # health checks fail fast rather than block on backoff
            allow_truncation=True,
        )
        return {**base, "reachable": True, "sample": sample[:40]}
    except httpx.HTTPStatusError as exc:
        failure: dict[str, Any] = {
            **base,
            "reachable": False,
            "error": f"HTTP {exc.response.status_code}: {str(exc)[:160]}",
        }
        if exc.response.status_code == 404:
            # The configured id is not one this subscription serves. Name the
            # ones it does, so the health endpoint carries the fix and not just
            # the symptom (BL-20260904-05). Best effort: /models may itself be
            # outside an account's allowlist.
            available = await _available_models_quietly()
            if available is not None:
                failure["available_models"] = available
        return failure
    except Exception as exc:  # pragma: no cover - defensive
        return {**base, "reachable": False, "error": str(exc)[:200]}


__all__ = [
    "PROVIDER_NAME",
    "XaiRefusalError",
    "XaiUnavailableError",
    "astream",
    "base_url",
    "generate",
    "interactive_model",
    "interactive_overrides",
    "list_models",
    "model",
    "model_label",
    "probe",
]
