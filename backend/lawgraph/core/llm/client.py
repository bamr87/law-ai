"""Unified Ollama LLM client (spec 024 FR-1..FR-4).

Single audited path to the product runtime LLM. Wraps the official
``ollama`` Python package (httpx-based, so connection pooling comes for
free) and adds the three things every scattered call site used to
re-implement by hand:

* **Retry** — exponential backoff on transient failures (connection
  refused, timeouts, 5xx). Client errors (4xx, malformed requests) are
  never retried.
* **Provenance** — every call appends an ``llm_call`` event via
  :mod:`lawgraph.core.audit_jsonl` (prompt/response hashes, latency,
  retries, caller label) and opens an OpenTelemetry span when the
  ``local-ai`` extra is installed (constitution §4 / NFR-AUDIT-1).
* **Streaming** — :meth:`LLMClient.generate_stream` yields raw text
  chunks so Channels consumers can forward token deltas (spec 022
  follow-ups BL-20260602-05/-06).

Errors are normalised to the :class:`LLMError` hierarchy so callers can
keep a single graceful-fallback ``except`` clause regardless of which
transport failed underneath.

Example::

    from lawgraph.core.llm import get_llm_client

    client = get_llm_client()
    text = await client.generate("Summarise Marbury v. Madison.",
                                 caller="legal_workflow")
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from lawgraph.core import audit_jsonl
from lawgraph.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("lawgraph.core.llm")

AGENT_VERSION = "lawgraph.core.llm.v1"

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMResponseError",
    "LLMUnavailableError",
    "get_llm_client",
    "reset_llm_client",
]


class LLMError(Exception):
    """Base class for every failure raised by :class:`LLMClient`."""


class LLMUnavailableError(LLMError):
    """Transient failure (connection refused, timeout, 5xx). Retried."""


class LLMResponseError(LLMError):
    """Non-transient failure (4xx, malformed request). Never retried."""


def _classify(exc: BaseException) -> LLMError:
    """Map an arbitrary transport exception onto the LLMError hierarchy.

    Anything carrying a 4xx ``status_code`` (e.g. ``ollama.ResponseError``
    for an unknown model) is a caller bug and must not be retried; every
    other failure is treated as transient.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return LLMResponseError(str(exc))
    return LLMUnavailableError(str(exc))


def _extract(payload: Any, key: str) -> Any:
    """Read ``key`` from an ollama response (pydantic model or dict)."""
    value = getattr(payload, key, None)
    if value is None and isinstance(payload, Mapping):
        value = payload.get(key)
    return value


def _stable_hash(payload: Any) -> str:
    from lawgraph.core.provenance import _stable_hash as impl

    return impl(payload)


def _otel_span(endpoint: str) -> Any:
    """Best-effort OTEL span; no-op when opentelemetry is not installed."""
    try:
        from opentelemetry import trace

        return trace.get_tracer("lawgraph.llm").start_as_current_span(
            f"llm.{endpoint}"
        )
    except Exception:  # pragma: no cover - optional dependency missing
        import contextlib

        return contextlib.nullcontext()


class LLMClient:
    """Audited, retrying client for the local Ollama runtime.

    All constructor arguments default to the Django settings so a bare
    ``LLMClient()`` (or the shared :func:`get_llm_client` instance) targets
    the configured local-first stack. Tests inject fakes via the
    ``async_client_factory`` / ``sync_client_factory`` seams — no network
    or ``ollama`` import is needed.

    :param host: Ollama base URL (default ``settings.OLLAMA_BASE_URL``).
    :param model: default model tag (``settings.OLLAMA_DEFAULT_MODEL``).
    :param timeout_s: per-request timeout (``settings.OLLAMA_REQUEST_TIMEOUT_S``).
    :param max_retries: extra attempts after the first failure (default 2).
    :param backoff_base_s: first retry delay; doubles per attempt.
    :param async_client_factory: returns an ``ollama.AsyncClient``-like object.
    :param sync_client_factory: returns an ``ollama.Client``-like object.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        backoff_base_s: float = 0.5,
        async_client_factory: Callable[[], Any] | None = None,
        sync_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._host = host or str(settings.OLLAMA_BASE_URL)
        self._model = model or str(settings.OLLAMA_DEFAULT_MODEL)
        self._timeout_s = (
            float(settings.OLLAMA_REQUEST_TIMEOUT_S)
            if timeout_s is None
            else float(timeout_s)
        )
        self._max_retries = (
            int(getattr(settings, "OLLAMA_MAX_RETRIES", 2))
            if max_retries is None
            else int(max_retries)
        )
        self._backoff_base_s = backoff_base_s
        self._async_client_factory = async_client_factory
        self._sync_client_factory = sync_client_factory
        self._async_client: Any | None = None
        self._sync_client: Any | None = None

    # -- transport ----------------------------------------------------------

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            if self._async_client_factory is not None:
                self._async_client = self._async_client_factory()
            else:
                import ollama

                self._async_client = ollama.AsyncClient(
                    host=self._host, timeout=self._timeout_s
                )
        return self._async_client

    def _get_sync_client(self) -> Any:
        if self._sync_client is None:
            if self._sync_client_factory is not None:
                self._sync_client = self._sync_client_factory()
            else:
                import ollama

                self._sync_client = ollama.Client(
                    host=self._host, timeout=self._timeout_s
                )
        return self._sync_client

    @staticmethod
    def _options(temperature: float | None) -> dict[str, Any] | None:
        return None if temperature is None else {"temperature": temperature}

    # -- retry loops ---------------------------------------------------------

    async def _with_retries(
        self, fn: Callable[[], Any], *, endpoint: str
    ) -> tuple[Any, int]:
        attempt = 0
        while True:
            try:
                return await fn(), attempt
            except LLMError:
                raise
            except Exception as exc:
                err = _classify(exc)
                if isinstance(err, LLMUnavailableError) and attempt < self._max_retries:
                    delay = self._backoff_base_s * (2**attempt)
                    attempt += 1
                    logger.info(
                        "llm.%s transient failure (attempt %d/%d, retry in %.2fs): %s",
                        endpoint,
                        attempt,
                        self._max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise err from exc

    def _with_retries_sync(
        self, fn: Callable[[], Any], *, endpoint: str
    ) -> tuple[Any, int]:
        attempt = 0
        while True:
            try:
                return fn(), attempt
            except LLMError:
                raise
            except Exception as exc:
                err = _classify(exc)
                if isinstance(err, LLMUnavailableError) and attempt < self._max_retries:
                    delay = self._backoff_base_s * (2**attempt)
                    attempt += 1
                    logger.info(
                        "llm.%s transient failure (attempt %d/%d, retry in %.2fs): %s",
                        endpoint,
                        attempt,
                        self._max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    continue
                raise err from exc

    # -- provenance -----------------------------------------------------------

    def _record(
        self,
        *,
        endpoint: str,
        model: str,
        caller: str,
        prompt_hash: str,
        response_hash: str | None,
        latency_ms: float,
        retries: int,
        error: str | None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "llm_call",
            "endpoint": endpoint,
            "model": model,
            "caller": caller,
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "latency_ms": round(latency_ms, 2),
            "retries": retries,
            "ok": error is None,
            "agent_version": AGENT_VERSION,
        }
        if prompt_id:
            event["prompt_id"] = prompt_id
        if prompt_version:
            event["prompt_version"] = prompt_version
        if error is not None:
            event["error"] = error[:500]
        audit_jsonl.record(event)

    # -- public API ------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_format: bool = False,
        caller: str = "unknown",
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> str:
        """One-shot completion via Ollama ``/api/generate``.

        Example::

            text = await client.generate("ping", caller="healthcheck")
        """
        used_model = model or self._model
        started = time.perf_counter()
        retries = 0
        error: str | None = None
        text = ""

        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": used_model,
                "prompt": prompt,
                "stream": False,
            }
            options = self._options(temperature)
            if options is not None:
                kwargs["options"] = options
            if json_format:
                kwargs["format"] = "json"
            return await self._get_async_client().generate(**kwargs)

        with _otel_span("generate"):
            try:
                resp, retries = await self._with_retries(_call, endpoint="generate")
                text = str(_extract(resp, "response") or "")
            except LLMError as exc:
                error = str(exc)
                raise
            finally:
                self._record(
                    endpoint="generate",
                    model=used_model,
                    caller=caller,
                    prompt_hash=_stable_hash(prompt),
                    response_hash=_stable_hash(text) if error is None else None,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    retries=retries,
                    error=error,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                )
        return text

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_format: bool = False,
        caller: str = "unknown",
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> AsyncIterator[str]:
        """Streaming completion — yields raw text chunks as they arrive.

        The retry policy applies to *opening* the stream only; once chunks
        flow, a mid-stream failure surfaces as :class:`LLMUnavailableError`
        without replay (callers own resume semantics).
        """
        used_model = model or self._model
        started = time.perf_counter()
        retries = 0
        error: str | None = None
        chunks = 0

        async def _open() -> Any:
            kwargs: dict[str, Any] = {
                "model": used_model,
                "prompt": prompt,
                "stream": True,
            }
            options = self._options(temperature)
            if options is not None:
                kwargs["options"] = options
            if json_format:
                kwargs["format"] = "json"
            return await self._get_async_client().generate(**kwargs)

        try:
            stream, retries = await self._with_retries(_open, endpoint="generate")
            async for part in stream:
                piece = str(_extract(part, "response") or "")
                if piece:
                    chunks += 1
                    yield piece
        except LLMError as exc:
            error = str(exc)
            raise
        except Exception as exc:
            error = str(exc)
            raise _classify(exc) from exc
        finally:
            self._record(
                endpoint="generate_stream",
                model=used_model,
                caller=caller,
                prompt_hash=_stable_hash(prompt),
                response_hash=f"chunks:{chunks}",
                latency_ms=(time.perf_counter() - started) * 1000.0,
                retries=retries,
                error=error,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )

    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_format: bool = False,
        caller: str = "unknown",
    ) -> str:
        """Multi-turn completion via Ollama ``/api/chat``.

        Example::

            text = await client.chat(
                [{"role": "user", "content": "hi"}], caller="tutor"
            )
        """
        used_model = model or self._model
        started = time.perf_counter()
        retries = 0
        error: str | None = None
        text = ""

        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": used_model,
                "messages": list(messages),
                "stream": False,
            }
            options = self._options(temperature)
            if options is not None:
                kwargs["options"] = options
            if json_format:
                kwargs["format"] = "json"
            return await self._get_async_client().chat(**kwargs)

        with _otel_span("chat"):
            try:
                resp, retries = await self._with_retries(_call, endpoint="chat")
                message = _extract(resp, "message")
                text = str(_extract(message, "content") or "") if message else ""
            except LLMError as exc:
                error = str(exc)
                raise
            finally:
                self._record(
                    endpoint="chat",
                    model=used_model,
                    caller=caller,
                    prompt_hash=_stable_hash(list(messages)),
                    response_hash=_stable_hash(text) if error is None else None,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    retries=retries,
                    error=error,
                )
        return text

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        caller: str = "unknown",
    ) -> list[list[float]]:
        """Embed ``texts`` via Ollama ``/api/embed`` (Phase-2 GraphRAG seam).

        :param model: embedding model tag; defaults to
            ``settings.OLLAMA_EMBED_MODEL`` when set, else the chat model.
        """
        used_model = model or str(
            getattr(settings, "OLLAMA_EMBED_MODEL", "") or self._model
        )
        started = time.perf_counter()
        retries = 0
        error: str | None = None
        vectors: list[list[float]] = []

        async def _call() -> Any:
            return await self._get_async_client().embed(
                model=used_model, input=list(texts)
            )

        with _otel_span("embed"):
            try:
                resp, retries = await self._with_retries(_call, endpoint="embed")
                raw = _extract(resp, "embeddings") or []
                vectors = [[float(v) for v in vec] for vec in raw]
            except LLMError as exc:
                error = str(exc)
                raise
            finally:
                self._record(
                    endpoint="embed",
                    model=used_model,
                    caller=caller,
                    prompt_hash=_stable_hash(list(texts)),
                    response_hash=f"vectors:{len(vectors)}",
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    retries=retries,
                    error=error,
                )
        return vectors

    def generate_sync(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_format: bool = False,
        caller: str = "unknown",
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> str:
        """Synchronous one-shot completion for non-async call sites.

        Used by the LegalBench CLI and the TopicFrontier prioritize node,
        which run outside an event loop. Same retry + provenance semantics
        as :meth:`generate`.
        """
        used_model = model or self._model
        started = time.perf_counter()
        retries = 0
        error: str | None = None
        text = ""

        def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": used_model,
                "prompt": prompt,
                "stream": False,
            }
            options = self._options(temperature)
            if options is not None:
                kwargs["options"] = options
            if json_format:
                kwargs["format"] = "json"
            return self._get_sync_client().generate(**kwargs)

        with _otel_span("generate"):
            try:
                resp, retries = self._with_retries_sync(_call, endpoint="generate")
                text = str(_extract(resp, "response") or "")
            except LLMError as exc:
                error = str(exc)
                raise
            finally:
                self._record(
                    endpoint="generate",
                    model=used_model,
                    caller=caller,
                    prompt_hash=_stable_hash(prompt),
                    response_hash=_stable_hash(text) if error is None else None,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    retries=retries,
                    error=error,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                )
        return text


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the shared settings-backed :class:`LLMClient` instance."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_llm_client() -> None:
    """Drop the shared instance (tests / settings reloads)."""
    global _default_client
    _default_client = None
