"""Shared LangChain LLM layer for Law AI agents (spec 027).

One transport for every Ollama-backed agent path: a ``ChatOllama`` runnable
wrapped with LangChain's tenacity-backed retry (constitution §8), plus a
cheap TTL-cached availability probe so callers can degrade honestly instead
of hanging or crashing when Ollama is down (constitution §13 — a refusal
must be a refusal, never a fabricated answer).

Import-safe without the ``local-ai`` extra: the heavy ``langchain_ollama``
import is deferred until a runnable is actually built. Callers that need to
work on a bare install should catch :class:`LLMUnavailableError`.

Usage::

    from law_ai.agents_runtime import llm

    if not llm.ollama_available():
        return degraded_output()
    runnable = llm.build_chat_ollama()          # retries built in
    text = llm.coerce_text(await runnable.ainvoke(prompt))
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

import httpx

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.agents_runtime.llm")

#: LangChain's ``with_retry`` uses tenacity under the hood (constitution §8).
RETRY_ATTEMPTS = 3

#: Availability probe cache lifetime. Long enough to keep per-request
#: overhead negligible, short enough that a restarted Ollama is noticed.
_PROBE_TTL_S = 15.0

_probe_cache: dict[str, tuple[float, bool]] = {}

#: Shared (L2) verdict keys this process has written, so the test helper can
#: clear them without knowing every URL that was probed.
_shared_probe_keys: set[str] = set()
_SHARED_PROBE_KEY = "ollama_probe:{url}"


class LLMUnavailableError(RuntimeError):
    """Raised when the LangChain/Ollama stack cannot be constructed.

    Most commonly the ``local-ai`` extra is not installed:
    ``pip install -e ".[dev,local-ai]"``.
    """


def _retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Transient error types worth retrying against a local Ollama."""
    types: tuple[type[BaseException], ...] = (TimeoutError, OSError, httpx.HTTPError)
    try:  # the ollama client lib raises its own ResponseError on 5xx
        from ollama import ResponseError

        types = (*types, ResponseError)
    except ImportError:  # pragma: no cover - client lib always ships with extra
        pass
    return types


def build_chat_ollama(
    *,
    model: str | None = None,
    temperature: float = 0.0,
    output_format: str | None = None,
    base_url: str | None = None,
    timeout_s: float | None = None,
    retries: int = RETRY_ATTEMPTS,
) -> Any:
    """Build a retry-wrapped ``ChatOllama`` runnable.

    Args:
        model: Ollama model tag; defaults to ``settings.OLLAMA_DEFAULT_MODEL``.
        temperature: sampling temperature (0.0 = deterministic-ish default).
        output_format: pass ``"json"`` to force Ollama's JSON mode.
        base_url: Ollama endpoint; defaults to ``settings.OLLAMA_BASE_URL``.
        timeout_s: per-request timeout; defaults to
            ``settings.OLLAMA_REQUEST_TIMEOUT_S``.
        retries: total attempts (LangChain ``with_retry``, exponential jitter).

    Returns:
        A LangChain runnable whose ``invoke``/``ainvoke`` accept a prompt
        string and retry transient failures.

    Raises:
        LLMUnavailableError: when ``langchain_ollama`` is not installed.

    Example::

        runnable = build_chat_ollama(output_format="json")
        answer = coerce_text(await runnable.ainvoke("Return {} as JSON"))
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise LLMUnavailableError(
            'langchain-ollama not installed — run `pip install -e ".[dev,local-ai]"`'
        ) from exc

    fmt: Literal["", "json"] = "json" if output_format == "json" else ""
    chat = ChatOllama(
        base_url=base_url or settings.OLLAMA_BASE_URL,
        model=model or settings.OLLAMA_DEFAULT_MODEL,
        temperature=temperature,
        format=fmt,
        client_kwargs={
            "timeout": (
                timeout_s
                if timeout_s is not None
                else float(settings.OLLAMA_REQUEST_TIMEOUT_S)
            )
        },
    )
    if retries <= 1:
        return chat
    return chat.with_retry(
        retry_if_exception_type=_retryable_exceptions(),
        stop_after_attempt=retries,
        wait_exponential_jitter=True,
    )


def coerce_text(message: Any) -> str:
    """Pull the textual payload out of whatever a LangChain LLM returns."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # pragma: no cover - LangChain message parts
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(message)


def generate_text_sync(
    prompt: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout_s: float | None = None,
    output_format: str | None = None,
) -> str:
    """Synchronous one-shot generation through the shared runnable.

    For sync call sites (Celery tasks, management commands). Async callers
    should use ``build_chat_ollama()`` + ``ainvoke`` directly.

    Example::

        code = generate_text_sync("Write a pytest skeleton", model="mistral")
    """
    runnable = build_chat_ollama(
        model=model,
        base_url=base_url,
        timeout_s=timeout_s,
        output_format=output_format,
    )
    return coerce_text(runnable.invoke(prompt))


def _shared_cache() -> Any:
    """The Django cache used as the cross-process (L2) probe store.

    Resolved lazily so importing this module never touches Django, and kept
    behind one function so tests can substitute a broken or shared backend.
    """
    from django.core.cache import cache

    return cache


def _shared_key(url: str) -> str:
    return _SHARED_PROBE_KEY.format(url=url)


def _l1_cached(url: str, ttl_s: float) -> bool | None:
    cached = _probe_cache.get(url)
    if cached is not None and (time.monotonic() - cached[0]) < ttl_s:
        return cached[1]
    return None


def _l2_adopt(url: str, entry: Any, ttl_s: float) -> bool | None:
    """Repopulate L1 from a shared entry, honouring its *remaining* TTL."""
    if not isinstance(entry, dict):
        return None
    try:
        up = bool(entry["up"])
        elapsed = max(0.0, time.time() - float(entry["at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if elapsed >= ttl_s:
        return None
    _probe_cache[url] = (time.monotonic() - elapsed, up)
    return up


def _probe_cached(url: str, ttl_s: float) -> bool | None:
    """Return the cached probe verdict for *url*, or None when stale/absent.

    L1 is the in-process dict; on a miss the shared Django cache (Redis in a
    multi-process deployment, BL-20260810-15) is consulted so daphne and every
    Celery worker agree on one verdict per TTL window instead of each probing.
    A cache failure is a miss — never an error in the request path.
    """
    cached = _l1_cached(url, ttl_s)
    if cached is not None:
        return cached
    try:
        entry = _shared_cache().get(_shared_key(url))
    except Exception:  # cache backend down/misconfigured → L1-only behaviour
        logger.debug("ollama probe: shared cache unavailable", exc_info=True)
        return None
    return _l2_adopt(url, entry, ttl_s)


async def _probe_cached_async(url: str, ttl_s: float) -> bool | None:
    """Async twin of :func:`_probe_cached` (non-blocking L2 read)."""
    cached = _l1_cached(url, ttl_s)
    if cached is not None:
        return cached
    try:
        entry = await _shared_cache().aget(_shared_key(url))
    except Exception:
        logger.debug("ollama probe: shared cache unavailable", exc_info=True)
        return None
    return _l2_adopt(url, entry, ttl_s)


def _shared_entry(up: bool) -> dict[str, Any]:
    return {"up": up, "at": time.time()}


def _probe_record(url: str, up: bool, ttl_s: float) -> bool:
    _probe_cache[url] = (time.monotonic(), up)
    if not up:
        logger.info("ollama probe: %s unreachable (cached %.0fs)", url, ttl_s)
    try:
        _shared_probe_keys.add(_shared_key(url))
        _shared_cache().set(_shared_key(url), _shared_entry(up), timeout=ttl_s)
    except Exception:
        logger.debug("ollama probe: could not share verdict", exc_info=True)
    return up


async def _probe_record_async(url: str, up: bool, ttl_s: float) -> bool:
    _probe_cache[url] = (time.monotonic(), up)
    if not up:
        logger.info("ollama probe: %s unreachable (cached %.0fs)", url, ttl_s)
    try:
        _shared_probe_keys.add(_shared_key(url))
        await _shared_cache().aset(_shared_key(url), _shared_entry(up), timeout=ttl_s)
    except Exception:
        logger.debug("ollama probe: could not share verdict", exc_info=True)
    return up


def ollama_available(
    *, base_url: str | None = None, ttl_s: float = _PROBE_TTL_S
) -> bool:
    """Cheap TTL-cached reachability probe for the Ollama server.

    Lets request paths degrade to an honest refusal in milliseconds instead
    of burning retry budget when Ollama is down. Not a model-presence check —
    eval paths must verify their model explicitly (BL-20260810-12).

    The verdict is cached in-process (L1) and shared through the Django cache
    (L2, Redis in production) under the same TTL, so a multi-process
    deployment probes once per window rather than once per worker.
    """
    url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
    cached = _probe_cached(url, ttl_s)
    if cached is not None:
        return cached
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=1.0)
        up = resp.status_code < 500
    except (httpx.HTTPError, OSError):
        up = False
    return _probe_record(url, up, ttl_s)


async def ollama_available_async(
    *, base_url: str | None = None, ttl_s: float = _PROBE_TTL_S
) -> bool:
    """Async twin of :func:`ollama_available` (shares the same TTL cache).

    Use from request handlers / async agents so the probe never blocks the
    event loop.
    """
    url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
    cached = await _probe_cached_async(url, ttl_s)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{url}/api/tags")
        up = resp.status_code < 500
    except (httpx.HTTPError, OSError):
        up = False
    return await _probe_record_async(url, up, ttl_s)


def reset_probe_cache() -> None:
    """Clear the availability cache — L1 and the shared keys (test helper)."""
    _probe_cache.clear()
    keys = list(_shared_probe_keys)
    _shared_probe_keys.clear()
    if not keys:
        return
    try:
        _shared_cache().delete_many(keys)
    except Exception:
        logger.debug("ollama probe: could not clear shared verdicts", exc_info=True)


__all__ = [
    "RETRY_ATTEMPTS",
    "LLMUnavailableError",
    "build_chat_ollama",
    "coerce_text",
    "generate_text_sync",
    "ollama_available",
    "ollama_available_async",
    "reset_probe_cache",
]
