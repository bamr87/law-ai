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
latency, and the full attempt chain, so a fallback is always visible after
the fact.

Usage::

    from law_ai.core import llm

    result = await llm.agenerate("Summarise this holding", system=SYS)
    text, label = result.text, result.model_label   # "claude_code/claude-opus-4-8"

Sync call sites (Celery tasks, management commands) use :func:`generate`.
LangGraph nodes that want a LangChain-shaped runnable use
:func:`build_runnable`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

from law_ai.core.llm.base import (
    LLMAttempt,
    LLMProvider,
    LLMRequest,
    LLMResult,
    LLMUnavailableError,
)
from law_ai.core.llm.providers import PROVIDER_REGISTRY
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.core.llm.router")

#: Chain used when ``LLM_PROVIDER_CHAIN`` is unset or parses to nothing.
DEFAULT_CHAIN: tuple[str, ...] = ("claude_code", "anthropic_api", "ollama")


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


def _log_call(
    *,
    request: LLMRequest,
    result: LLMResult | None,
    attempts: Sequence[LLMAttempt],
    agent: str | None,
) -> None:
    """Write one ``llm_call`` provenance event (success or total failure)."""
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
            }
            for a in attempts
        ],
        "prompt_chars": len(request.prompt),
        "json_mode": request.wants_json(),
        "ok": result is not None,
    }
    if result is not None:
        payload.update(
            provider=result.provider,
            model=result.model,
            model_label=result.model_label,
            latency_ms=round(result.latency_ms, 2),
            fell_back=result.fell_back,
            output_chars=len(result.text),
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
    """
    providers = build_chain(request.providers)
    attempts: list[LLMAttempt] = []

    for provider in providers:
        if not provider.configured():
            reason = provider.unconfigured_reason() or "not configured"
            attempts.append(
                LLMAttempt(provider=provider.name, ok=False, skipped_reason=reason)
            )
            logger.debug("llm chain: skipping %s (%s)", provider.name, reason)
            continue

        started = time.monotonic()
        try:
            text = await provider.agenerate(request)
        except Exception as exc:
            attempts.append(
                LLMAttempt(
                    provider=provider.name,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
            )
            logger.info(
                "llm chain: %s failed (%s); trying next provider",
                provider.name,
                type(exc).__name__,
            )
            continue

        attempts.append(LLMAttempt(provider=provider.name, ok=True))
        result = LLMResult(
            text=text,
            provider=provider.name,
            model=provider.model_for(request),
            latency_ms=(time.monotonic() - started) * 1000.0,
            attempts=tuple(attempts),
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
    "build_chain",
    "build_runnable",
    "chain_names",
    "chain_status",
    "generate",
]
