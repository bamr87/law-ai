"""CourtListener REST API client (T-002 from specs/001).

Async, retrying, provenance-logged client over the public `v4/opinions`
endpoint. Constitution §8 requires `httpx` + `tenacity`; do not swap
them out without an ADR.
"""

from __future__ import annotations

import logging
from typing import Any
from collections.abc import AsyncIterator

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.ingestion.courtlistener")

BASE_URL = "https://www.courtlistener.com/api/rest/v4"
DEFAULT_TIMEOUT = 30.0


class CourtListenerError(RuntimeError):
    """Raised on non-retryable CourtListener API failures."""


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient network and 5xx + 429 responses only."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class CourtListenerClient:
    """Thin async wrapper around `https://www.courtlistener.com/api/rest/v4/`."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        api_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_token = (
            api_token if api_token is not None else settings.COURTLISTENER_API_KEY
        )
        self._timeout = timeout
        self._owns_client = client is None
        headers = {"Accept": "application/json", "User-Agent": "law-ai/0.1"}
        if self._api_token:
            headers["Authorization"] = f"Token {self._api_token}"
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, headers=headers
        )

    async def __aenter__(self) -> CourtListenerClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(path, params=params)
                if response.status_code >= 400:
                    if not _is_retryable(
                        httpx.HTTPStatusError(
                            "non-retryable", request=response.request, response=response
                        )
                    ):
                        raise CourtListenerError(
                            f"CourtListener {response.status_code} for {path}: "
                            f"{response.text[:200]}"
                        )
                    response.raise_for_status()
                provenance.log_graph_query(  # reuse generic external-call audit
                    cypher=f"GET {path}",
                    params=params or {},
                    result_count=1,
                    latency_ms=response.elapsed.total_seconds() * 1000,
                )
                return response.json()
        # Pragma: tenacity reraises before reaching here.
        raise RetryError("unreachable")  # pragma: no cover

    async def fetch_opinion(self, opinion_id: int | str) -> dict[str, Any]:
        """Fetch a single opinion by id."""
        return await self._get(f"/opinions/{opinion_id}/")

    async def list_opinions(
        self, *, limit: int = 500, page_size: int = 50, **filters: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield up to ``limit`` opinions, paging the cursor-style API."""
        emitted = 0
        params: dict[str, Any] = {"page_size": min(page_size, limit), **filters}
        path: str | None = "/opinions/"
        while path and emitted < limit:
            payload = await self._get(
                path, params=params if path == "/opinions/" else None
            )
            for opinion in payload.get("results", []):
                yield opinion
                emitted += 1
                if emitted >= limit:
                    return
            next_url = payload.get("next")
            if not next_url:
                return
            # Strip base URL so we can reuse the bound client.
            path = (
                next_url.replace(self._base_url, "")
                if next_url.startswith(self._base_url)
                else next_url
            )
            params = None
