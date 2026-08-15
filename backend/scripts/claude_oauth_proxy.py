"""Claude OAuth sidecar proxy for the Phoenix playground (spec 038).

Arize Phoenix's playground can only authenticate to Anthropic with a plain
API key sent as ``x-api-key``. The product's tier-1 credential is a Claude
subscription OAuth token, which the API only accepts as ``Authorization:
Bearer`` plus the ``anthropic-beta: oauth-2025-04-20`` header (see
``law_ai.core.claude_code`` — sending the wrong pair is a 401).

This module is a tiny ASGI passthrough that bridges the two: it listens
inside the compose network only, strips whatever credential headers the
caller sent (Phoenix sends a placeholder ``x-api-key``), injects the OAuth
pair from ``CLAUDE_CODE_OAUTH_TOKEN``, and streams the upstream response
back unchanged (SSE included). The token therefore never enters Phoenix's
UI, browser storage, or database.

Run (compose service ``claude-oauth-proxy``)::

    python -m daphne -b 0.0.0.0 -p 8080 scripts.claude_oauth_proxy:application

Not a ``law_ai`` feature module: nothing in the product runtime calls this —
it exists solely so the observability playground can exercise the same
credential tier as the runtime chain. Playground calls do NOT pass through
``law_ai.core.llm`` and are not provenance-audited; request lines are logged
to stdout (``docker compose logs claude-oauth-proxy``) instead.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger("claude_oauth_proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

_OAUTH_BETA = "oauth-2025-04-20"
_DEFAULT_UPSTREAM = "https://api.anthropic.com"
_TIMEOUT = httpx.Timeout(600.0, connect=10.0)

#: Request headers never forwarded upstream: credentials are replaced with the
#: OAuth pair, and hop-by-hop/transport headers are recomputed by httpx.
_DROP_REQUEST_HEADERS = {
    "authorization",
    "x-api-key",
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "anthropic-beta",  # merged, not dropped — see _merged_beta()
}

#: Response headers safe to relay. Everything transport-related is owned by
#: the proxy's own server; content-encoding is omitted because httpx already
#: decoded the stream (we request identity encoding upstream anyway).
#: ``retry-after`` matters: subscription OAuth tokens rate-limit aggressively
#: and callers need the backoff hint.
_RELAY_RESPONSE_HEADERS = {"content-type", "cache-control", "request-id", "retry-after"}

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_client: httpx.AsyncClient | None = None


def _upstream_base() -> str:
    return (os.environ.get("ANTHROPIC_BASE_URL") or _DEFAULT_UPSTREAM).rstrip("/")


def _token() -> str:
    return (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=_upstream_base(), timeout=_TIMEOUT)
    return _client


def _merged_beta(incoming: list[str]) -> str:
    """OAuth beta flag plus whatever beta features the caller asked for."""
    values = [_OAUTH_BETA]
    for raw in incoming:
        for part in raw.split(","):
            flag = part.strip()
            if flag and flag != _OAUTH_BETA:
                values.append(flag)
    return ",".join(values)


def _build_headers(scope: Scope) -> dict[str, str]:
    incoming: list[tuple[str, str]] = [
        (k.decode("latin-1").lower(), v.decode("latin-1"))
        for k, v in scope.get("headers", [])
    ]
    headers = {k: v for k, v in incoming if k not in _DROP_REQUEST_HEADERS}
    headers["authorization"] = f"Bearer {_token()}"
    headers["anthropic-beta"] = _merged_beta(
        [v for k, v in incoming if k == "anthropic-beta"]
    )
    headers.setdefault("anthropic-version", "2023-06-01")
    headers["accept-encoding"] = "identity"
    return headers


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            return b"".join(chunks)


async def _respond(
    send: Send, status: int, body: bytes, content_type: str = "application/json"
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type.encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def application(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if _client is not None:
                    await _client.aclose()
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return

    path: str = scope["path"]
    if path in ("/", "/health"):
        ok = bool(_token())
        await _respond(
            send,
            200 if ok else 503,
            b'{"status": "ok"}' if ok else b'{"status": "no CLAUDE_CODE_OAUTH_TOKEN"}',
        )
        return
    if not _token():
        await _respond(
            send, 503, b'{"error": "CLAUDE_CODE_OAUTH_TOKEN is not set in .env"}'
        )
        return

    body = await _read_body(receive)
    url = path + (
        "?" + scope["query_string"].decode() if scope.get("query_string") else ""
    )
    request = _get_client().build_request(
        scope["method"], url, content=body, headers=_build_headers(scope)
    )
    try:
        upstream = await _get_client().send(request, stream=True)
    except httpx.HTTPError as exc:
        logger.warning("%s %s -> upstream error %s", scope["method"], path, exc)
        await _respond(send, 502, b'{"error": "upstream unreachable"}')
        return

    try:
        headers = [
            (k.encode(), v.encode())
            for k, v in upstream.headers.items()
            if k.lower() in _RELAY_RESPONSE_HEADERS
        ]
        await send(
            {
                "type": "http.response.start",
                "status": upstream.status_code,
                "headers": headers,
            }
        )
        async for chunk in upstream.aiter_bytes():
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b""})
        logger.info("%s %s -> %s", scope["method"], path, upstream.status_code)
    finally:
        await upstream.aclose()
