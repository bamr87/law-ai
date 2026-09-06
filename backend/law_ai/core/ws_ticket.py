"""Short-lived tickets for the agent-run WebSocket (BL-20260430-07).

Why a ticket exists at all
--------------------------
A browser cannot set headers on a WebSocket handshake, so the stream used to
carry the shared API key in the query string — which meant the key had to be
in the browser bundle (``NEXT_PUBLIC_AGENT_API_KEY``). Moving the REST calls
behind the Next.js proxy took the key out of the bundle; a socket that still
needed the raw key would have put it straight back.

So the frontend's server side (which does hold ``AGENT_API_KEY``) mints a
ticket the browser can spend exactly once, on one stream, within a minute:

    ticket = "<expiry-unix>.<hex HMAC-SHA256(secret, stream_id + '.' + expiry)>"

Properties that matter:

* **Scoped** — the stream id is signed, so a ticket for one run cannot be
  replayed against another.
* **Short-lived** — an expiry in the past is refused, so a ticket leaked from
  a browser history or a proxy log is worthless within the minute.
* **Stateless** — verification needs only the shared secret, so nothing has to
  be stored or replicated between the two processes.

It is *not* a session: it says "the holder of AGENT_API_KEY vouched for this
stream", which is exactly what the raw key said, minus the permanence.
"""

from __future__ import annotations

import hashlib
import hmac
import time

#: How long a freshly minted ticket stays valid. Long enough for a page to
#: open its socket, short enough that a leaked one is already dead.
DEFAULT_TTL_SECONDS = 60

#: A ticket from a clock that runs ahead of ours is still accepted this far
#: out — clock skew between two containers is not an attack.
MAX_SKEW_SECONDS = 300


def sign(stream_id: str, expiry: int, secret: str) -> str:
    """The HMAC half of a ticket for ``stream_id``/``expiry``."""
    message = f"{stream_id}.{expiry}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def mint_ticket(
    stream_id: str,
    secret: str,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """A ticket for ``stream_id``. The frontend proxy mints these in TypeScript;
    this exists so the contract has one executable definition and tests do not
    hand-roll the format."""
    expiry = int((time.time() if now is None else now) + ttl)
    return f"{expiry}.{sign(stream_id, expiry, secret)}"


def verify_ticket(
    ticket: str | None, stream_id: str, secret: str, *, now: float | None = None
) -> bool:
    """True when ``ticket`` was minted for ``stream_id`` and has not expired.

    Every failure — malformed, wrong stream, wrong secret, expired — returns
    False rather than raising: this runs on an unauthenticated handshake, and
    an exception there is a crash an anonymous client can trigger.
    """
    if not ticket or not secret:
        return False
    head, _, mac = ticket.partition(".")
    if not mac:
        return False
    try:
        expiry = int(head)
    except ValueError:
        return False

    clock = time.time() if now is None else now
    if expiry < clock or expiry > clock + MAX_SKEW_SECONDS:
        return False
    return hmac.compare_digest(mac, sign(stream_id, expiry, secret))
