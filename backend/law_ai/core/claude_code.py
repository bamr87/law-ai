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
from typing import Any, Literal

import httpx

from law_ai.core.settings_proxy import settings_proxy as settings

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


def is_selected() -> bool:
    """True iff an operator has explicitly pinned the legacy LSAT provider.

    Legacy escape hatch: ``LSAT_LLM_PROVIDER`` predates the provider chain and
    now only matters when someone pins a single provider for the LSAT surface.
    The chain in ``LLM_PROVIDER_CHAIN`` is the real selector.
    """
    provider = str(getattr(settings, "LSAT_LLM_PROVIDER", "claude_code") or "").lower()
    return provider == PROVIDER_NAME


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
        raise ClaudeCodeUnavailableError(
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
                return _extract_text(resp.json(), allow_truncation=allow_truncation)
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
