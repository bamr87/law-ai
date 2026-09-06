"""The LLM provider chain: route, fall back, and audit every call (spec 034).

One entry point for every model call in the product. The chain is read from
``LLM_PROVIDER_CHAIN`` (default ``claude_code,anthropic_api,ollama``) and tried
in order: the first provider that is configured *and* answers wins; each
failure is recorded and the next provider is tried. When every provider fails
the router raises :class:`LLMUnavailableError` carrying the per-provider
reasons, so callers degrade to an honest refusal rather than a fabrication
(constitution §13).

Every call is written to the audit layer via ``ProvenanceLogger.log_event``
before the result is returned (constitution §5 — no LLM call bypasses
provenance). The event records the provider that served it, the model, the
latency, the full attempt chain, and — when the transport reported them — the
input/output token counts plus a ``cost_usd`` priced from the optional
``LLM_PRICE_TABLE`` setting, so a fallback is always visible after the fact and
hosted-tier spend is attributable per agent (BL-20260811-21).

Failures are classified permanent (a rejected credential, a request the
provider will not parse, a model it does not serve) or transient (timeouts,
429/5xx after the transport's own retries). The chain still falls through on
both — constitution §13 prefers a local answer to no answer — but a permanent
*credential* failure is remembered for ``LLM_PERMANENT_FAILURE_TTL_S`` so the
next request skips that tier instead of re-earning the same 401, is warned
about once per window, and shows up in :func:`chain_status` for the health
endpoint. Deployments that would rather fail loudly than answer from a
lower tier set ``LLM_FAIL_FAST_ON_PERMANENT=true`` and get
:class:`LLMPermanentError` instead (BL-20260811-23).

Usage::

    from law_ai.core import llm

    result = await llm.agenerate("Summarise this holding", system=SYS)
    text, label = result.text, result.model_label   # "claude_code/claude-opus-4-8"

Sync call sites (Celery tasks, management commands) use :func:`generate`.
LangGraph nodes that want a LangChain-shaped runnable use
:func:`build_runnable`.

:func:`astream` is the same chain, token by token (BL-20260811-20). It falls
back exactly like :func:`aroute` up to the first delta and refuses to after
it: once a caller has seen text, restarting on another tier would splice two
answers together, so the failure surfaces as
:class:`~law_ai.core.llm.base.LLMStreamInterrupted` carrying what was already
sent. Streamed calls write the same ``llm_call`` event, marked
``streamed: true``, when the stream ends.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from law_ai.core.claude_code import ClaudeCredentialError
from law_ai.core.llm.base import (
    LLMAttempt,
    LLMChunk,
    LLMPermanentError,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMStreamInterrupted,
    LLMUnavailableError,
)
from law_ai.core.llm.providers import PROVIDER_REGISTRY
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.usage import LLMUsage, usage_of

logger = logging.getLogger("law_ai.core.llm.router")

#: Chain used when ``LLM_PROVIDER_CHAIN`` is unset or parses to nothing.
#: xAI joined as tier 3 in spec 050 (constitution §1, amended 2026-09-04); it is
#: inert until an operator authorises it, so an unconfigured deployment behaves
#: exactly as it did before.
DEFAULT_CHAIN: tuple[str, ...] = ("claude_code", "anthropic_api", "xai", "ollama")


def chain_names(override: Sequence[str] | None = None) -> tuple[str, ...]:
    """Resolve the ordered provider names for this process.

    Unknown tokens are dropped with a warning rather than raising — a typo in
    an env var must not take the whole runtime down, it should degrade to the
    providers that *are* recognised.
    """
    if override is not None:
        raw: Sequence[str] = override
    else:
        configured = str(getattr(settings, "LLM_PROVIDER_CHAIN", "") or "")
        raw = [p.strip() for p in configured.split(",")] if configured else []

    names: list[str] = []
    for token in raw:
        name = token.strip().lower()
        if not name:
            continue
        if name not in PROVIDER_REGISTRY:
            logger.warning("ignoring unknown LLM provider %r in chain", name)
            continue
        if name not in names:  # de-dupe, keep first position
            names.append(name)
    return tuple(names) or DEFAULT_CHAIN


def build_chain(override: Sequence[str] | None = None) -> tuple[LLMProvider, ...]:
    """Instantiate the resolved chain, in order."""
    providers: list[LLMProvider] = []
    for name in chain_names(override):
        provider: LLMProvider = PROVIDER_REGISTRY[name]()
        providers.append(provider)
    return tuple(providers)


#: Attempt kinds recorded on :class:`LLMAttempt` and the ``llm_call`` event.
PERMANENT = "permanent"
TRANSIENT = "transient"

#: HTTP statuses that no amount of retrying or waiting can fix: a rejected
#: credential (401/403), a malformed request or unsupported parameter (400,
#: 422), an unknown model or endpoint (404).
_PERMANENT_STATUS = frozenset({400, 401, 403, 404, 422})

#: The subset of the above that indicts the *tier* rather than the request, so
#: it is worth remembering and skipping. A 400 means this prompt was wrong; a
#: 401 means every prompt will be.
_AUTH_STATUS = frozenset({401, 403})

#: provider name -> (epoch seconds, reason) for the last credential failure.
#: Per-process on purpose: it is a cheap way to stop hammering a rejected key,
#: not a distributed circuit breaker, and it must not outlive a redeploy that
#: fixes the credential.
_permanent_failures: dict[str, tuple[float, str]] = {}


def classify_failure(exc: BaseException) -> str:
    """Say whether *exc* is worth retrying elsewhere or is a misconfiguration.

    Permanent means "the same call will fail the same way until a human
    changes something": a rejected or absent credential, a request the
    provider refuses to parse, a model id it does not serve. Everything else —
    timeouts, dropped connections, 429/5xx after the transport's own retries —
    is transient (BL-20260811-23).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return PERMANENT if status in _PERMANENT_STATUS else TRANSIENT
    if _is_credential_failure(exc):
        return PERMANENT
    return TRANSIENT


def _is_credential_failure(exc: BaseException) -> bool:
    """True when *exc* says the tier's credential itself is unusable."""
    from law_ai.core.xai_oauth import XaiAuthError

    if isinstance(exc, ClaudeCredentialError | XaiAuthError | LLMPermanentError):
        return True
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _AUTH_STATUS
    )


def _permanent_ttl() -> float:
    return float(getattr(settings, "LLM_PERMANENT_FAILURE_TTL_S", 300.0) or 0.0)


def _fail_fast() -> bool:
    return bool(getattr(settings, "LLM_FAIL_FAST_ON_PERMANENT", False))


def _remember_permanent(provider: str, exc: BaseException) -> None:
    """Record a credential failure and warn once per TTL window."""
    ttl = _permanent_ttl()
    if ttl <= 0:
        return
    previous = _permanent_failures.get(provider)
    now = time.time()
    if previous is not None and (now - previous[0]) < ttl:
        return  # already warned about this one in this window
    reason = f"{type(exc).__name__}: {exc}"[:200]
    _permanent_failures[provider] = (now, reason)
    logger.warning(
        "llm chain: %s credential rejected (%s); skipping the tier for %.0fs",
        provider,
        reason,
        ttl,
    )


def _permanent_skip_reason(provider: str) -> str | None:
    """Why *provider* is being skipped after a recent credential failure."""
    entry = _permanent_failures.get(provider)
    if entry is None:
        return None
    at, reason = entry
    if (time.time() - at) >= _permanent_ttl():
        _permanent_failures.pop(provider, None)
        return None
    stamp = datetime.fromtimestamp(at, tz=UTC).isoformat(timespec="seconds")
    return f"auth failed at {stamp}: {reason}"


def reset_permanent_failures() -> None:
    """Forget every remembered credential failure (test helper, and the hook
    an operator-facing 'retry now' would call after fixing a key)."""
    _permanent_failures.clear()


def _skip_reason(provider: LLMProvider) -> str | None:
    """Why this provider should not be called at all, if it should not be."""
    if not provider.configured():
        return provider.unconfigured_reason() or "not configured"
    return _permanent_skip_reason(provider.name)


def _record_failure(
    provider: str, exc: BaseException, attempts: list[LLMAttempt]
) -> str:
    """Append the failed attempt, remembering a credential failure. Returns kind."""
    kind = classify_failure(exc)
    if kind == PERMANENT and _is_credential_failure(exc):
        _remember_permanent(provider, exc)
    attempts.append(
        LLMAttempt(
            provider=provider,
            ok=False,
            error=f"{type(exc).__name__}: {exc}"[:300],
            kind=kind,
        )
    )
    logger.info(
        "llm chain: %s failed (%s, %s); trying next provider",
        provider,
        type(exc).__name__,
        kind,
    )
    return kind


def _price_entry(provider: str, model: str) -> Mapping[str, Any] | None:
    """The ``LLM_PRICE_TABLE`` row for one call, most specific key first.

    Keys are looked up as ``provider/model``, then ``model``, then ``provider``,
    so an operator can price a single model precisely or a whole tier roughly.
    Prices are configuration, never code: they go stale, and a wrong number
    baked into a release would be worse than no number at all.
    """
    table = getattr(settings, "LLM_PRICE_TABLE", None)
    if not isinstance(table, Mapping):
        return None
    for key in (f"{provider}/{model}", model, provider):
        entry = table.get(key)
        if isinstance(entry, Mapping):
            return entry
    return None


def estimate_cost_usd(
    provider: str, model: str, usage: LLMUsage | None
) -> float | None:
    """USD cost of one call, or ``None`` when it cannot be priced.

    Returns ``None`` — never zero — when usage is missing or the model is not
    in the price table, so an unpriced tier reads as unpriced in the audit log
    instead of looking free.
    """
    if usage is None:
        return None
    entry = _price_entry(provider, model)
    if entry is None:
        return None
    total = 0.0
    priced = False
    rates = (
        (usage.input_tokens, entry.get("in_per_mtok")),
        (usage.output_tokens, entry.get("out_per_mtok")),
    )
    for tokens, rate in rates:
        if tokens is None or rate is None:
            continue
        try:
            total += (float(tokens) / 1_000_000.0) * float(rate)
        except (TypeError, ValueError):
            return None
        priced = True
    return round(total, 8) if priced else None


def _usage_payload(result: LLMResult) -> dict[str, Any]:
    """Token/cost fields for the ``llm_call`` event of a successful call."""
    usage = result.usage
    return {
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "total_tokens": usage.total_tokens if usage else None,
        "cost_usd": estimate_cost_usd(result.provider, result.model, usage),
    }


def _log_call(
    *,
    request: LLMRequest,
    result: LLMResult | None,
    attempts: Sequence[LLMAttempt],
    agent: str | None,
    streamed: bool = False,
    partial_chars: int | None = None,
) -> None:
    """Write one ``llm_call`` provenance event (success or total failure).

    ``streamed`` marks a call served token-by-token, and ``partial_chars``
    records how much text a caller had already received when a stream broke —
    the one failure mode where the product emitted real model output and still
    has no result (BL-20260811-20).
    """
    from law_ai.core.provenance import ProvenanceLogger

    payload: dict[str, Any] = {
        "agent": agent,
        "chain": [a.provider for a in attempts],
        "attempts": [
            {
                "provider": a.provider,
                "ok": a.ok,
                "error": a.error,
                "skipped_reason": a.skipped_reason,
                "kind": a.kind,
            }
            for a in attempts
        ],
        "prompt_chars": len(request.prompt),
        "prompt_id": request.prompt_id,
        "prompt_version": request.prompt_version,
        "json_mode": request.wants_json(),
        "ok": result is not None,
        "streamed": streamed,
    }
    if partial_chars is not None:
        payload["partial_chars"] = partial_chars
    if result is not None:
        payload.update(
            provider=result.provider,
            model=result.model,
            model_label=result.model_label,
            latency_ms=round(result.latency_ms, 2),
            fell_back=result.fell_back,
            output_chars=len(result.text),
            **_usage_payload(result),
        )
    try:
        ProvenanceLogger.log_event("llm_call", payload)
    except Exception:  # pragma: no cover - audit must never break a request
        logger.warning("failed to write llm_call provenance event", exc_info=True)


async def aroute(request: LLMRequest, *, agent: str | None = None) -> LLMResult:
    """Run *request* down the chain and return the first success.

    Args:
        request: the provider-neutral request.
        agent: optional caller name, recorded on the provenance event.

    Raises:
        LLMUnavailableError: when every provider is unconfigured or failing.
        LLMPermanentError: when a provider fails permanently and
            ``LLM_FAIL_FAST_ON_PERMANENT`` is set (a subclass of the above, so
            existing handlers keep working).
    """
    providers = build_chain(request.providers)
    attempts: list[LLMAttempt] = []

    for provider in providers:
        reason = _skip_reason(provider)
        if reason is not None:
            attempts.append(
                LLMAttempt(provider=provider.name, ok=False, skipped_reason=reason)
            )
            logger.debug("llm chain: skipping %s (%s)", provider.name, reason)
            continue

        started = time.monotonic()
        try:
            reply = await provider.agenerate(request)
        except Exception as exc:
            kind = _record_failure(provider.name, exc, attempts)
            if kind == PERMANENT and _fail_fast():
                _log_call(request=request, result=None, attempts=attempts, agent=agent)
                raise LLMPermanentError(
                    f"{provider.name} failed permanently and "
                    "LLM_FAIL_FAST_ON_PERMANENT is set "
                    f"({type(exc).__name__}: {exc})"[:300],
                    attempts,
                ) from exc
            continue

        attempts.append(LLMAttempt(provider=provider.name, ok=True))
        result = LLMResult(
            text=str(reply),
            provider=provider.name,
            model=provider.model_for(request),
            latency_ms=(time.monotonic() - started) * 1000.0,
            attempts=tuple(attempts),
            usage=usage_of(reply),
        )
        _log_call(request=request, result=result, attempts=attempts, agent=agent)
        return result

    _log_call(request=request, result=None, attempts=attempts, agent=agent)
    detail = "; ".join(
        f"{a.provider}: {a.skipped_reason or a.error or 'failed'}" for a in attempts
    )
    raise LLMUnavailableError(
        f"no LLM provider could serve the request ({detail or 'empty chain'})",
        attempts,
    )


@dataclass
class _StreamAccum:
    """What one provider's stream produced so far, for the audit event."""

    started: float
    text: str = ""
    usage: LLMUsage | None = None
    first_seen: bool = False


async def _provider_deltas(
    provider: LLMProvider, request: LLMRequest
) -> AsyncIterator[str]:
    """Text deltas from *provider*, streaming when it can and buffering when not.

    A transport with no ``astream`` (a test double, a future provider) is not
    an error: its whole reply is yielded as one delta, so every tier is
    streamable from the caller's point of view and the chain keeps its shape.
    """
    stream = getattr(provider, "astream", None)
    if stream is None:
        yield await provider.agenerate(request)
        return
    async for delta in stream(request):
        yield delta


def _absorb(acc: _StreamAccum, delta: str) -> bool:
    """Fold one delta into *acc*; True when it should be yielded onward."""
    usage = usage_of(delta)
    if usage is not None:
        acc.usage = usage
    if not delta:
        return False
    acc.text += str(delta)
    return True


def _stream_result(
    provider: str, model: str, acc: _StreamAccum, attempts: Sequence[LLMAttempt]
) -> LLMResult:
    return LLMResult(
        text=acc.text,
        provider=provider,
        model=model,
        latency_ms=(time.monotonic() - acc.started) * 1000.0,
        attempts=tuple(attempts),
        usage=acc.usage,
        streamed=True,
    )


def _stream_failed(
    *,
    provider: LLMProvider,
    exc: Exception,
    acc: _StreamAccum,
    attempts: list[LLMAttempt],
    request: LLMRequest,
    agent: str | None,
) -> None:
    """Record a failed stream and decide whether the chain may continue.

    Returns normally when the next tier should be tried; raises when it must
    not be. The dividing line is whether the caller already saw a token: after
    that, falling through would splice a second provider's answer onto the
    first, so :class:`LLMStreamInterrupted` carries the partial text instead.
    """
    kind = _record_failure(provider.name, exc, attempts)
    if acc.first_seen:
        _log_call(
            request=request,
            result=None,
            attempts=attempts,
            agent=agent,
            streamed=True,
            partial_chars=len(acc.text),
        )
        raise LLMStreamInterrupted(
            f"{provider.name} stream failed after {len(acc.text)} chars "
            f"({type(exc).__name__}: {exc})"[:300],
            attempts,
            partial=acc.text,
        ) from exc
    if kind == PERMANENT and _fail_fast():
        _log_call(
            request=request, result=None, attempts=attempts, agent=agent, streamed=True
        )
        raise LLMPermanentError(
            f"{provider.name} failed permanently and "
            "LLM_FAIL_FAST_ON_PERMANENT is set "
            f"({type(exc).__name__}: {exc})"[:300],
            attempts,
        ) from exc


async def aroute_stream(
    request: LLMRequest, *, agent: str | None = None
) -> AsyncIterator[LLMChunk]:
    """Stream *request* down the chain, yielding deltas as they arrive.

    Fallback semantics are the whole design here (BL-20260811-20). A provider
    that fails **before its first token** is treated exactly as
    :func:`aroute` treats a failed call: recorded, skipped, next tier. A
    provider that fails **after** one is not retried anywhere — the caller (and
    in the WebSocket path, a human) has already seen text, and restarting on
    another tier would stitch two answers together. That failure raises
    :class:`LLMStreamInterrupted` carrying the partial text.

    One ``llm_call`` provenance event is written when the stream ends —
    success or interruption — with ``streamed: true``, so a streamed call is
    as auditable as a buffered one and distinguishable from it (constitution
    §5).
    """
    attempts: list[LLMAttempt] = []

    for provider in build_chain(request.providers):
        reason = _skip_reason(provider)
        if reason is not None:
            attempts.append(
                LLMAttempt(provider=provider.name, ok=False, skipped_reason=reason)
            )
            logger.debug("llm stream: skipping %s (%s)", provider.name, reason)
            continue

        acc = _StreamAccum(started=time.monotonic())
        model = provider.model_for(request)
        try:
            async for delta in _provider_deltas(provider, request):
                if not _absorb(acc, delta):
                    continue
                first, acc.first_seen = not acc.first_seen, True
                yield LLMChunk(
                    text=str(delta),
                    provider=provider.name,
                    model=model,
                    first=first,
                )
        except Exception as exc:
            _stream_failed(
                provider=provider,
                exc=exc,
                acc=acc,
                attempts=attempts,
                request=request,
                agent=agent,
            )
            continue

        attempts.append(LLMAttempt(provider=provider.name, ok=True))
        _log_call(
            request=request,
            result=_stream_result(provider.name, model, acc, attempts),
            attempts=attempts,
            agent=agent,
            streamed=True,
        )
        return

    _log_call(
        request=request, result=None, attempts=attempts, agent=agent, streamed=True
    )
    detail = "; ".join(
        f"{a.provider}: {a.skipped_reason or a.error or 'failed'}" for a in attempts
    )
    raise LLMUnavailableError(
        f"no LLM provider could stream the request ({detail or 'empty chain'})",
        attempts,
    )


def astream(
    prompt: str,
    *,
    system: str | None = None,
    response_schema: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    models: Mapping[str, str] | None = None,
    providers: Sequence[str] | None = None,
    agent: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
) -> AsyncIterator[LLMChunk]:
    """Convenience wrapper over :func:`aroute_stream` for the common call shape.

    Streaming is opt-in per call site on purpose: a caller that parses the
    reply as JSON (``coerce_text``, the LSAT factory executors) cannot consume
    partial text, so those paths keep calling :func:`agenerate`.
    """
    request = LLMRequest(
        prompt=prompt,
        system=system,
        response_schema=response_schema,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
        models=dict(models or {}),
        providers=providers,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )
    return aroute_stream(request, agent=agent)


async def agenerate(
    prompt: str,
    *,
    system: str | None = None,
    response_schema: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    models: Mapping[str, str] | None = None,
    providers: Sequence[str] | None = None,
    agent: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
) -> LLMResult:
    """Convenience wrapper over :func:`aroute` for the common call shape."""
    request = LLMRequest(
        prompt=prompt,
        system=system,
        response_schema=response_schema,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
        models=dict(models or {}),
        providers=providers,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )
    return await aroute(request, agent=agent)


def generate(
    prompt: str,
    *,
    system: str | None = None,
    response_schema: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_mode: bool = False,
    models: Mapping[str, str] | None = None,
    providers: Sequence[str] | None = None,
    agent: str | None = None,
) -> LLMResult:
    """Synchronous :func:`agenerate` for Celery tasks and management commands.

    Raises:
        RuntimeError: when called from inside a running event loop — async
            call sites must await :func:`agenerate` instead of blocking it.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "llm.generate() is sync-only; await llm.agenerate() from async code"
        )
    return asyncio.run(
        agenerate(
            prompt,
            system=system,
            response_schema=response_schema,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            models=models,
            providers=providers,
            agent=agent,
        )
    )


async def chain_status() -> list[dict[str, Any]]:
    """Probe every provider in the chain, in order, for the health endpoint."""
    providers = build_chain()
    probes = await asyncio.gather(
        *(p.probe() for p in providers), return_exceptions=True
    )
    out: list[dict[str, Any]] = []
    for position, (provider, probe) in enumerate(zip(providers, probes, strict=True)):
        entry: dict[str, Any] = {
            "provider": provider.name,
            "position": position,
            "configured": provider.configured(),
        }
        # A configured-but-rejected credential is invisible to a reachability
        # probe, so surface the remembered failure: /api/health is where an
        # operator finds out the key is wrong (BL-20260811-23).
        skipped = _permanent_skip_reason(provider.name)
        if skipped is not None:
            entry["last_permanent_error"] = skipped
        if isinstance(probe, BaseException):  # pragma: no cover - defensive
            entry.update(reachable=False, error=str(probe)[:200])
        else:
            entry.update(probe)
        out.append(entry)
    return out


class ChainRunnable:
    """LangChain-shaped adapter so LangGraph nodes can call the chain.

    Exposes the ``invoke``/``ainvoke`` pair ``law_ai.agents_runtime.graphs``
    already programs against, so those nodes gain Claude-first routing without
    changing their call style. Returns the raw string; ``llm.coerce_text``
    accepts strings unchanged, so existing coercion still works.
    """

    def __init__(
        self,
        *,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        models: Mapping[str, str] | None = None,
        providers: Sequence[str] | None = None,
        agent: str | None = None,
    ) -> None:
        self._kwargs: dict[str, Any] = {
            "system": system,
            "json_mode": json_mode,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "models": dict(models or {}),
            "providers": providers,
            "agent": agent,
        }

    async def ainvoke(self, prompt: str) -> str:
        result = await agenerate(prompt, **self._kwargs)
        return result.text

    def invoke(self, prompt: str) -> str:
        return generate(prompt, **self._kwargs).text


def build_runnable(**kwargs: Any) -> ChainRunnable:
    """Build a :class:`ChainRunnable` bound to the configured chain."""
    return ChainRunnable(**kwargs)


__all__ = [
    "DEFAULT_CHAIN",
    "ChainRunnable",
    "agenerate",
    "aroute",
    "aroute_stream",
    "astream",
    "build_chain",
    "build_runnable",
    "chain_names",
    "chain_status",
    "classify_failure",
    "estimate_cost_usd",
    "generate",
    "reset_permanent_failures",
]
