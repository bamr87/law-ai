"""Ollama reachability probe shared by the agent paths (spec 027).

A cheap TTL-cached availability check so callers can degrade honestly instead
of hanging or crashing when Ollama is down (constitution §13 — a refusal must
be a refusal, never a fabricated answer), plus :func:`coerce_text` for
LangChain-shaped replies.

There is exactly **one** Ollama transport in the tree, and it is not here: the
chain's :class:`law_ai.core.llm.providers.OllamaProvider` (BL-20260810-05).
The ``ChatOllama``/``with_retry`` runnable this module used to build was a
second, parallel transport with no production callers, so it was removed
rather than left as a fork of the shared client; the one remaining direct
``/api/generate`` caller is the LegalBench harness, which is pinned to Ollama
on purpose so benchmark numbers stay comparable.

Usage::

    from law_ai.agents_runtime import llm

    if not llm.ollama_available():
        return degraded_output()
    text = await core_llm.agenerate(prompt)     # the shared chain client
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.agents_runtime.llm")

#: Availability probe cache lifetime. Long enough to keep per-request
#: overhead negligible, short enough that a restarted Ollama is noticed.
_PROBE_TTL_S = 15.0

_probe_cache: dict[str, tuple[float, bool]] = {}

#: Shared (L2) verdict keys this process has written, so the test helper can
#: clear them without knowing every URL that was probed.
_shared_probe_keys: set[str] = set()
_SHARED_PROBE_KEY = "ollama_probe:{url}"


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
    "coerce_text",
    "ollama_available",
    "ollama_available_async",
    "reset_probe_cache",
]
