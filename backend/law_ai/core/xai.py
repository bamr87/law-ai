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
from typing import Any

import httpx

from law_ai.core import xai_oauth
from law_ai.core.settings_proxy import settings_proxy as settings

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


def model_label() -> str:
    """Audit-friendly identifier recorded as the producing model."""
    return f"{PROVIDER_NAME}/{model()}"


def base_url() -> str:
    return str(getattr(settings, "XAI_BASE_URL", "https://api.x.ai/v1")).rstrip("/")


def _completions_url() -> str:
    return f"{base_url()}/chat/completions"


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
                return _extract_text(resp.json(), allow_truncation=allow_truncation)
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
        return {
            **base,
            "reachable": False,
            "error": f"HTTP {exc.response.status_code}: {str(exc)[:160]}",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {**base, "reachable": False, "error": str(exc)[:200]}


__all__ = [
    "PROVIDER_NAME",
    "XaiRefusalError",
    "XaiUnavailableError",
    "base_url",
    "generate",
    "model",
    "model_label",
    "probe",
]
