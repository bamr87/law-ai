"""Claude Code OAuth provider — **dev-time only** LLM alternative to Ollama.

Lets a developer point the LSAT tutor at their local Claude Code OAuth
subscription instead of a running Ollama instance, e.g. when iterating on
laptops without the local model stack up. It talks to the Anthropic Messages
API the same way the Claude Code CLI does: an OAuth bearer token (minted with
``claude setup-token`` and exported as ``CLAUDE_CODE_OAUTH_TOKEN``) plus the
``oauth-2025-04-20`` beta header — **not** an API key.

Constitution guardrail (docs/constitution.md §1, AGENTS.md "Development
Orchestration"): Claude is a **dev-time** tool and MUST NEVER be the product
runtime LLM. This module enforces that — :func:`is_active` returns ``False``
unless the process is running in a development environment AND an operator has
explicitly opted in via ``LSAT_LLM_PROVIDER=claude_code`` AND a token is
present. Outside development the provider refuses to engage and the caller
falls back to Ollama / the deterministic offline path. Ollama stays the
default product runtime; this is purely a local developer convenience.

The client mirrors :mod:`law_ai.lsat.services.tutor`'s lightweight Ollama
client (raw ``httpx``, no SDK dependency) so the bare backend image keeps
booting without extra packages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.core.claude_code")

PROVIDER_NAME = "claude_code"

# OAuth tokens are scoped to the Claude Code surface, so the Messages API
# requires the request to identify as Claude Code: the first system block must
# be exactly this line. We prepend it automatically to every request.
CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."

# Beta header the Claude Code CLI sends so OAuth bearer tokens are accepted on
# /v1/messages (an API key would use x-api-key instead).
_OAUTH_BETA_HEADER = "oauth-2025-04-20"
_ANTHROPIC_VERSION = "2023-06-01"

# Keep the health probe near-free: one or two output tokens is enough to prove
# the OAuth round-trip works without spending real budget on dashboard polls.
_PROBE_MAX_TOKENS = 8

# Transient Anthropic statuses worth retrying with backoff (429 rate limit,
# 529 overloaded, and 5xx). The official SDK retries these automatically; the
# raw httpx client here does the same so a passing overload doesn't degrade a
# whole agent run to the offline fallback.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})

# Development environment markers (mirrors settings/dev.py's ENVIRONMENT value).
_DEV_ENVIRONMENTS = frozenset({"development", "dev", "local"})


class ClaudeCodeUnavailableError(RuntimeError):
    """Raised when a Claude Code call is attempted without a usable config."""


# ---------------------------------------------------------------------------
# Gating helpers (the constitution lives here)
# ---------------------------------------------------------------------------


def oauth_token() -> str | None:
    """Return the configured OAuth token, or ``None`` when unset/blank."""
    token = getattr(settings, "CLAUDE_CODE_OAUTH_TOKEN", "") or ""
    return token.strip() or None


def is_development() -> bool:
    """True iff the process is running in a development environment.

    Hard gate for the constitution's "dev-time only" rule. Either ``DEBUG`` is
    on or ``ENVIRONMENT`` names a dev profile; production/test never qualify.
    """
    if bool(getattr(settings, "DEBUG", False)):
        return True
    env = str(getattr(settings, "ENVIRONMENT", "") or "").lower()
    return env in _DEV_ENVIRONMENTS


def is_selected() -> bool:
    """True iff an operator has opted Claude Code in as the LSAT provider."""
    provider = str(getattr(settings, "LSAT_LLM_PROVIDER", "ollama") or "ollama").lower()
    return provider == PROVIDER_NAME


def is_active() -> bool:
    """True iff Claude Code should serve the LSAT tutor for this request.

    All three must hold: opted in, in development, and a token is present.
    The tutor checks this to decide whether to route to Claude Code; any
    ``False`` keeps Ollama as the product runtime.
    """
    return is_selected() and is_development() and oauth_token() is not None


def inactive_reason() -> str | None:
    """Explain why :func:`is_active` is ``False`` (for logs / the validator)."""
    if not is_selected():
        return "LSAT_LLM_PROVIDER is not 'claude_code' (Ollama remains the default)"
    if not is_development():
        return (
            "refusing outside development — Claude Code is a dev-time tool only "
            "(constitution §1); the product runtime stays Ollama"
        )
    if oauth_token() is None:
        return "CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`)"
    return None


def model() -> str:
    """The configured Claude model id (e.g. ``claude-opus-4-8``)."""
    return str(getattr(settings, "CLAUDE_CODE_MODEL", "claude-opus-4-8"))


def model_label() -> str:
    """Audit-friendly identifier recorded as the producing model."""
    return f"{PROVIDER_NAME}/{model()}"


# ---------------------------------------------------------------------------
# Messages API client (OAuth, mirrors the Ollama httpx pattern)
# ---------------------------------------------------------------------------


def _messages_url() -> str:
    base = str(getattr(settings, "ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    return base.rstrip("/") + "/v1/messages"


def _extract_text(data: dict[str, Any]) -> str:
    """Concatenate the ``text`` blocks of a Messages API response."""
    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "".join(parts).strip()


def strip_code_fence(text: str) -> str:
    """Drop a leading ```/```json fence + trailing ``` if a model added one.

    Chat models often wrap JSON in a markdown fence even when asked not to;
    both the LSAT tutor and content author feed responses to ``json.loads``,
    so they share this normalizer.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s.split("\n", 1)[1] if "\n" in s else ""
    if s.rstrip().endswith("```"):
        s = s.rstrip()[: -len("```")]
    return s.strip()


def loads_first_json(text: str) -> Any:
    """Parse the first decodable JSON value in ``text``, tolerating chatty models.

    Strips a markdown fence, then tries ``raw_decode`` at each ``{``/``[`` so
    that leading prose (even prose containing a stray brace) and trailing
    commentary or a second object — which ``json.loads`` rejects as "Extra
    data" — are both handled. Raises :class:`json.JSONDecodeError` when no
    decodable JSON value is present. This is a defensive net; the Claude Code
    path additionally pins output with a ``response_schema`` (structured
    outputs) so the response is schema-valid JSON to begin with.
    """
    s = strip_code_fence(text)
    decoder = json.JSONDecoder()
    last_err: json.JSONDecodeError | None = None
    for i, ch in enumerate(s):
        if ch not in "{[":
            continue
        try:
            obj, _end = decoder.raw_decode(s[i:])
            return obj
        except json.JSONDecodeError as exc:
            last_err = exc
    raise last_err or json.JSONDecodeError("no JSON object found", s or text, 0)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``retry-after`` header (integer seconds) if the server sent one."""
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
    response_schema: dict[str, Any] | None = None,
    max_retries: int | None = None,
) -> str:
    """Call the Anthropic Messages API over OAuth and return the text reply.

    Pass ``response_schema`` (a JSON Schema) to constrain the reply to
    schema-valid JSON via structured outputs — the reliable way to get parseable
    JSON out of a chat model. Transient errors (429/5xx/529) are retried with
    exponential backoff (``CLAUDE_CODE_MAX_RETRIES``, overridable per call).
    Raises :class:`ClaudeCodeUnavailableError` when no token is configured and
    re-raises ``httpx`` errors so callers can fall back gracefully (the LSAT
    tutor catches these like Ollama failures).
    """
    token = oauth_token()
    if token is None:
        raise ClaudeCodeUnavailableError(
            "CLAUDE_CODE_OAUTH_TOKEN is not set; run `claude setup-token`"
        )

    system_blocks: list[dict[str, str]] = [
        {"type": "text", "text": CLAUDE_CODE_IDENTITY}
    ]
    if system:
        system_blocks.append({"type": "text", "text": system})

    payload: dict[str, Any] = {
        "model": model_id or model(),
        "max_tokens": max_tokens
        or int(getattr(settings, "CLAUDE_CODE_MAX_TOKENS", 2048)),
        "system": system_blocks,
        "messages": [{"role": "user", "content": prompt}],
    }
    if response_schema is not None:
        payload["output_config"] = {
            "format": {"type": "json_schema", "schema": response_schema}
        }
    headers = {
        "authorization": f"Bearer {token}",
        "anthropic-version": _ANTHROPIC_VERSION,
        "anthropic-beta": _OAUTH_BETA_HEADER,
        "content-type": "application/json",
    }
    timeout = httpx.Timeout(
        float(getattr(settings, "CLAUDE_CODE_REQUEST_TIMEOUT_S", 60.0))
    )
    attempts = max(
        1,
        (
            max_retries
            if max_retries is not None
            else int(getattr(settings, "CLAUDE_CODE_MAX_RETRIES", 3))
        ),
    )
    url = _messages_url()
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return _extract_text(resp.json())
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in _RETRYABLE_STATUS or attempt == attempts - 1:
                    raise
                wait = _retry_after_seconds(exc.response) or float(2**attempt)
                logger.info(
                    "Claude Code HTTP %s; retry %s/%s in %.1fs",
                    status,
                    attempt + 1,
                    attempts,
                    wait,
                )
                await asyncio.sleep(wait)
            except httpx.TransportError as exc:
                if attempt == attempts - 1:
                    raise
                logger.info(
                    "Claude Code transport error (%s); retry %s/%s",
                    type(exc).__name__,
                    attempt + 1,
                    attempts,
                )
                await asyncio.sleep(float(2**attempt))
    # Unreachable: the loop either returns or raises on the final attempt.
    raise ClaudeCodeUnavailableError("exhausted retries without a response")


async def probe() -> dict[str, Any]:
    """Reachability probe for the local-ai health endpoint.

    Performs a near-free OAuth round-trip (a couple of output tokens) when the
    dev gate + token are in place, so the dashboard can confirm the connection
    without spending real budget. Never raises — failures are reported inline.
    """
    selected = is_selected()
    dev = is_development()
    token_present = oauth_token() is not None

    base: dict[str, Any] = {
        "provider": PROVIDER_NAME,
        "selected": selected,
        "development": dev,
        "token_present": token_present,
        "model": model(),
    }

    if not dev:
        return {
            **base,
            "reachable": False,
            "reason": "disabled outside development (constitution §1)",
        }
    if not token_present:
        return {
            **base,
            "reachable": False,
            "reason": "CLAUDE_CODE_OAUTH_TOKEN not set",
        }

    try:
        sample = await generate(
            "Reply with the single word: pong",
            system="You are a connectivity probe. Reply with exactly one word.",
            max_tokens=_PROBE_MAX_TOKENS,
            max_retries=1,  # health checks fail fast rather than block on backoff
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
