"""Anthropic Claude transport — the product runtime's primary LLM (spec 034).

Talks to the Anthropic Messages API under either of two auth modes:

* ``oauth`` — a Claude subscription token minted with ``claude setup-token``
  and exported as ``CLAUDE_CODE_OAUTH_TOKEN``, sent as a bearer token with the
  ``oauth-2025-04-20`` beta header. This is the chain's first choice.
* ``api_key`` — a standard ``ANTHROPIC_API_KEY`` sent as ``x-api-key``. Same
  models, same response shape; the chain's second choice when OAuth is absent
  or failing.

OAuth tokens are scoped to the Claude Code surface, so that mode additionally
prepends the required identity system block; the API-key mode does not (a
plain API request has no reason to claim to be a CLI).

Constitution note (docs/constitution.md §1, amended 2026-08-11): Claude is the
**default product runtime**, with the Anthropic API key and then local Ollama
as fallbacks. The dev-only gate this module used to enforce has been repealed;
provider selection and fallback now live in :mod:`law_ai.core.llm.router`.

The client stays raw ``httpx`` (no SDK dependency) so the bare backend image
keeps booting without extra packages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from law_ai.core import sse
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.usage import LLMUsage, ProviderReply

logger = logging.getLogger("law_ai.core.claude_code")

PROVIDER_NAME = "claude_code"

#: Which credential a request authenticates with. "oauth" = a Claude
#: subscription token; "api_key" = a standard ANTHROPIC_API_KEY.
AuthMode = Literal["oauth", "api_key"]

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


class ClaudeCredentialError(ClaudeCodeUnavailableError):
    """No usable Claude credential — configuration, not an outage.

    A subclass so every existing ``except ClaudeCodeUnavailableError`` keeps
    working, while the router can tell a missing/rejected key (permanent: no
    retry, no other tier will fix it) from a transient transport failure
    (BL-20260811-23).
    """


class ClaudeRefusalError(RuntimeError):
    """Raised when Claude's safety classifiers decline the request.

    A declined request is a **successful HTTP 200** carrying
    ``stop_reason: "refusal"`` and an empty or partial ``content`` — code that
    reads the text blocks unconditionally would hand the caller a silently
    blank answer. Raising instead lets the provider chain fall through to the
    next tier, and lets the caller degrade to an honest refusal rather than a
    fabricated one (constitution §13).
    """

    def __init__(self, category: str | None = None) -> None:
        self.category = category
        super().__init__(
            f"Claude declined the request (category={category or 'unspecified'})"
        )


# ---------------------------------------------------------------------------
# Gating helpers (the constitution lives here)
# ---------------------------------------------------------------------------


def oauth_token() -> str | None:
    """Return the configured OAuth subscription token, or ``None`` when unset."""
    token = getattr(settings, "CLAUDE_CODE_OAUTH_TOKEN", "") or ""
    return token.strip() or None


def api_key() -> str | None:
    """Return the configured ``ANTHROPIC_API_KEY``, or ``None`` when unset."""
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    return key.strip() or None


def credential(auth: AuthMode) -> str | None:
    """Return the credential backing *auth*, or ``None`` when it is unset."""
    return oauth_token() if auth == "oauth" else api_key()


def is_development() -> bool:
    """True iff the process is running in a development environment.

    No longer a gate on Claude usage (constitution §1 was amended to make
    Claude the default runtime) — retained because the health probe and the
    validate command still report which environment they ran in.
    """
    if bool(getattr(settings, "DEBUG", False)):
        return True
    env = str(getattr(settings, "ENVIRONMENT", "") or "").lower()
    return env in _DEV_ENVIRONMENTS


def is_active() -> bool:
    """True iff the OAuth transport has a usable credential.

    Kept for the management commands that report provider state. Callers that
    want the *routed* answer should ask :mod:`law_ai.core.llm.router` instead —
    a missing OAuth token no longer means "no Claude", because the API-key
    provider may still serve the request.
    """
    return oauth_token() is not None


def inactive_reason() -> str | None:
    """Explain why :func:`is_active` is ``False`` (for logs / the validator)."""
    if oauth_token() is None:
        return (
            "CLAUDE_CODE_OAUTH_TOKEN is not set (run `claude setup-token`); "
            "the chain will fall back to ANTHROPIC_API_KEY, then Ollama"
        )
    return None


def model() -> str:
    """The configured Claude model id (e.g. ``claude-opus-5-5``)."""
    return str(getattr(settings, "CLAUDE_CODE_MODEL", "claude-opus-5-5"))


def model_label() -> str:
    """Audit-friendly identifier recorded as the producing model."""
    return f"{PROVIDER_NAME}/{model()}"


# ---------------------------------------------------------------------------
# Messages API client (OAuth, mirrors the Ollama httpx pattern)
# ---------------------------------------------------------------------------


def _messages_url() -> str:
    base = str(getattr(settings, "ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    return base.rstrip("/") + "/v1/messages"


def _extract_text(data: dict[str, Any], *, allow_truncation: bool = False) -> str:
    """Concatenate the ``text`` blocks of a Messages API response.

    Guards ``stop_reason`` first: a refusal carries empty/partial content and
    must not be mistaken for an answer, and a ``max_tokens`` stop means the
    payload is truncated — for a JSON-schema call that is a broken document,
    so both raise rather than returning a misleading string.
    """
    stop_reason = data.get("stop_reason")
    if stop_reason == "refusal":
        details = data.get("stop_details") or {}
        raise ClaudeRefusalError(details.get("category"))

    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    text = "".join(parts).strip()

    if stop_reason == "max_tokens" and not allow_truncation:
        raise ClaudeCodeUnavailableError(
            "response truncated at max_tokens "
            f"({len(text)} chars) — raise CLAUDE_CODE_MAX_TOKENS"
        )
    return text


def _extract_usage(data: dict[str, Any]) -> LLMUsage | None:
    """Read the Messages API ``usage`` block into provider-neutral counts.

    Anthropic reports ``input_tokens``/``output_tokens`` (plus cache counters
    this product does not bill separately yet). Absent or malformed usage
    yields ``None`` rather than raising — a billed call that succeeded must not
    fail on its accounting (BL-20260811-21).
    """
    return LLMUsage.from_payload(
        data.get("usage"),
        input_key="input_tokens",
        output_key="output_tokens",
    )


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


def _build_payload(
    prompt: str,
    *,
    system: str | None,
    model_id: str | None,
    max_tokens: int | None,
    response_schema: dict[str, Any] | None,
    auth: AuthMode,
    effort: str | None,
) -> dict[str, Any]:
    """Assemble the Messages API request body."""
    # Only the OAuth surface requires the Claude Code identity block; a plain
    # API-key request is an ordinary API call and must not claim to be a CLI.
    system_blocks: list[dict[str, str]] = []
    if auth == "oauth":
        system_blocks.append({"type": "text", "text": CLAUDE_CODE_IDENTITY})
    if system:
        system_blocks.append({"type": "text", "text": system})

    payload: dict[str, Any] = {
        "model": model_id or model(),
        "max_tokens": max_tokens
        or int(getattr(settings, "CLAUDE_CODE_MAX_TOKENS", 8192)),
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_blocks:
        payload["system"] = system_blocks

    # `output_config` carries both the structured-output format and the effort
    # level, so build it once rather than assigning it twice.
    output_config: dict[str, Any] = {}
    if response_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": response_schema}
    resolved_effort = effort or str(getattr(settings, "CLAUDE_EFFORT", "") or "")
    if resolved_effort:
        output_config["effort"] = resolved_effort
    if output_config:
        payload["output_config"] = output_config
    return payload


def _build_headers(secret: str, auth: AuthMode) -> dict[str, str]:
    """Auth headers for the chosen credential.

    OAuth tokens go on ``Authorization: Bearer`` plus the Claude Code beta
    header; an API key goes on ``x-api-key``. Sending the wrong pair is a 401.
    """
    headers = {
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    if auth == "oauth":
        headers["authorization"] = f"Bearer {secret}"
        headers["anthropic-beta"] = _OAUTH_BETA_HEADER
    else:
        headers["x-api-key"] = secret
    return headers


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
    response_schema: dict[str, Any] | None = None,
    max_retries: int | None = None,
    auth: AuthMode = "oauth",
    effort: str | None = None,
    allow_truncation: bool = False,
) -> str:
    """Call the Anthropic Messages API and return the text reply.

    The return value is a :class:`~law_ai.core.usage.ProviderReply` — a ``str``
    that also carries the response's token usage, so the router can bill the
    call to an agent without any caller having to change.

    ``auth`` picks the credential: ``"oauth"`` (a Claude subscription token,
    the chain's first choice) or ``"api_key"`` (``ANTHROPIC_API_KEY``).

    Note there is deliberately no ``temperature``/``top_p``/``top_k``: those
    parameters were removed on Claude Opus 5 / 4.8 / 4.7 and now return a 400.
    Steer output through the prompt and ``effort`` instead.

    Pass ``response_schema`` (a JSON Schema) to constrain the reply to
    schema-valid JSON via structured outputs — the reliable way to get parseable
    JSON out of a chat model. Transient errors (429/5xx/529) are retried with
    exponential backoff (``CLAUDE_CODE_MAX_RETRIES``, overridable per call).
    Raises :class:`ClaudeCodeUnavailableError` when no token is configured and
    re-raises ``httpx`` errors so callers can fall back gracefully (the LSAT
    tutor catches these like Ollama failures).
    """
    secret = credential(auth)
    if secret is None:
        raise ClaudeCredentialError(
            "CLAUDE_CODE_OAUTH_TOKEN is not set; run `claude setup-token`"
            if auth == "oauth"
            else "ANTHROPIC_API_KEY is not set"
        )

    payload = _build_payload(
        prompt,
        system=system,
        model_id=model_id,
        max_tokens=max_tokens,
        response_schema=response_schema,
        auth=auth,
        effort=effort,
    )
    headers = _build_headers(secret, auth)
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
                data = resp.json()
                return ProviderReply(
                    _extract_text(data, allow_truncation=allow_truncation),
                    _extract_usage(data),
                )
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


@dataclass
class _StreamState:
    """Mutable accounting for one SSE feed (stop reason, usage, size)."""

    stop_reason: str | None = None
    refusal_category: str | None = None
    input_tokens: Any = None
    output_tokens: Any = None
    chars: int = 0


def _sse_deltas(line: str, state: _StreamState) -> list[str]:
    """Text deltas carried by one SSE line, updating *state* in place.

    Split out of :func:`astream` so the event grammar is unit-testable without
    a socket, and so the generator stays under ruff's branch cap.
    """
    event = sse.data_payload(line)
    if event is None:
        return []

    kind = event.get("type")
    if kind == "content_block_delta":
        return _text_delta(event, state)
    if kind == "message_start":
        usage = (event.get("message") or {}).get("usage") or {}
        state.input_tokens = usage.get("input_tokens")
    elif kind == "message_delta":
        _absorb_message_delta(event, state)
    elif kind == "error":
        detail = str((event.get("error") or {}).get("message") or "stream error")
        raise ClaudeCodeUnavailableError(f"Claude stream error: {detail[:200]}")
    return []


def _text_delta(event: dict[str, Any], state: _StreamState) -> list[str]:
    """The text of one ``content_block_delta``, ignoring non-text blocks."""
    delta = event.get("delta") or {}
    if delta.get("type") != "text_delta":
        return []  # thinking / tool-use blocks are not part of the answer text
    text = str(delta.get("text") or "")
    state.chars += len(text)
    return [text] if text else []


def _absorb_message_delta(event: dict[str, Any], state: _StreamState) -> None:
    """Record the terminal stop reason and output token count."""
    delta = event.get("delta") or {}
    if delta.get("stop_reason"):
        state.stop_reason = str(delta["stop_reason"])
        details = delta.get("stop_details") or {}
        state.refusal_category = details.get("category")
    usage = event.get("usage") or {}
    if usage.get("output_tokens") is not None:
        state.output_tokens = usage.get("output_tokens")
    if usage.get("input_tokens") is not None and state.input_tokens is None:
        state.input_tokens = usage.get("input_tokens")


async def astream(
    prompt: str,
    *,
    system: str | None = None,
    model_id: str | None = None,
    max_tokens: int | None = None,
    response_schema: dict[str, Any] | None = None,
    auth: AuthMode = "oauth",
    effort: str | None = None,
    allow_truncation: bool = False,
) -> AsyncIterator[str]:
    """Stream the Messages API reply as text deltas (BL-20260811-20).

    Same request body as :func:`generate` plus ``stream: true``; the response
    is an SSE feed whose ``content_block_delta`` events carry the text. The
    terminal ``message_delta`` carries ``stop_reason`` and the output token
    count, so the refusal / truncation guards :func:`_extract_text` applies to
    a buffered reply are applied here too — at the end, which is the earliest a
    stream can know them.

    Deliberately **not** retried. A retry after the first delta would replay
    tokens the caller has already rendered; the chain's own fallback covers a
    failure *before* the first delta, and after that
    :class:`~law_ai.core.llm.base.LLMStreamInterrupted` is the honest outcome.

    The final delta is an empty :class:`~law_ai.core.usage.ProviderReply`
    carrying the call's token usage.
    """
    secret = credential(auth)
    if secret is None:
        raise ClaudeCredentialError(
            "CLAUDE_CODE_OAUTH_TOKEN is not set; run `claude setup-token`"
            if auth == "oauth"
            else "ANTHROPIC_API_KEY is not set"
        )

    payload = _build_payload(
        prompt,
        system=system,
        model_id=model_id,
        max_tokens=max_tokens,
        response_schema=response_schema,
        auth=auth,
        effort=effort,
    )
    payload["stream"] = True
    headers = _build_headers(secret, auth)
    headers["accept"] = "text/event-stream"
    timeout = httpx.Timeout(
        float(getattr(settings, "CLAUDE_CODE_REQUEST_TIMEOUT_S", 60.0))
    )

    state = _StreamState()
    async with (
        httpx.AsyncClient(timeout=timeout) as client,
        client.stream("POST", _messages_url(), json=payload, headers=headers) as resp,
    ):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            for delta in _sse_deltas(line, state):
                yield delta

    if state.stop_reason == "refusal":
        raise ClaudeRefusalError(state.refusal_category)
    if state.stop_reason == "max_tokens" and not allow_truncation:
        raise ClaudeCodeUnavailableError(
            f"streamed response truncated at max_tokens ({state.chars} chars) "
            "— raise CLAUDE_CODE_MAX_TOKENS"
        )
    yield ProviderReply(
        "", LLMUsage.from_counts(state.input_tokens, state.output_tokens)
    )


async def probe(*, auth: AuthMode = "oauth") -> dict[str, Any]:
    """Reachability probe for the local-ai health endpoint.

    Performs a near-free round-trip (a couple of output tokens) when a
    credential for *auth* is present, so the dashboard can confirm the
    connection without spending real budget. Never raises — failures are
    reported inline so one dead provider cannot fail the health response.
    """
    secret_present = credential(auth) is not None
    base: dict[str, Any] = {
        "provider": PROVIDER_NAME if auth == "oauth" else "anthropic_api",
        "auth": auth,
        "credential_present": secret_present,
        "development": is_development(),
        "model": model(),
    }

    if not secret_present:
        return {
            **base,
            "reachable": False,
            "reason": (
                "CLAUDE_CODE_OAUTH_TOKEN not set"
                if auth == "oauth"
                else "ANTHROPIC_API_KEY not set"
            ),
        }

    try:
        sample = await generate(
            "Reply with the single word: pong",
            system="You are a connectivity probe. Reply with exactly one word.",
            max_tokens=_PROBE_MAX_TOKENS,
            max_retries=1,  # health checks fail fast rather than block on backoff
            auth=auth,
            # Thinking is on by default on current Claude models and counts
            # against max_tokens, so a probe reliably stops at the cap. That
            # still proves the credential and the round-trip work.
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
