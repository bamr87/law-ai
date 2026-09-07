"""WebSocket ticket contract (BL-20260430-07).

The ticket is the credential that replaced the API key in the browser bundle,
so its failure modes matter more than its happy path: every one of them must
be a quiet ``False``, on an unauthenticated handshake, with no exception a
stranger can trigger.
"""

from __future__ import annotations

import time

import pytest

from law_ai.core.ws_ticket import DEFAULT_TTL_SECONDS, mint_ticket, sign, verify_ticket

SECRET = "secret-key"


def test_round_trip() -> None:
    assert verify_ticket(mint_ticket("run-abc", SECRET), "run-abc", SECRET)


def test_is_scoped_to_one_stream() -> None:
    ticket = mint_ticket("run-abc", SECRET)
    assert not verify_ticket(ticket, "run-other", SECRET)


def test_is_scoped_to_the_secret() -> None:
    ticket = mint_ticket("run-abc", SECRET)
    assert not verify_ticket(ticket, "run-abc", "another-key")


def test_expires() -> None:
    now = time.time()
    ticket = mint_ticket("run-abc", SECRET, ttl=DEFAULT_TTL_SECONDS, now=now)
    assert verify_ticket(ticket, "run-abc", SECRET, now=now + DEFAULT_TTL_SECONDS - 1)
    assert not verify_ticket(
        ticket, "run-abc", SECRET, now=now + DEFAULT_TTL_SECONDS + 1
    )


def test_refuses_an_absurdly_distant_expiry() -> None:
    """A forged far-future expiry buys nothing even before the MAC is checked."""
    far = int(time.time()) + 86_400
    forged = f"{far}.{sign('run-abc', far, SECRET)}"
    assert not verify_ticket(forged, "run-abc", SECRET)


@pytest.mark.parametrize(
    "ticket",
    [None, "", "no-dot", "notanumber.abcdef", "1700000000.", ".abcdef"],
)
def test_malformed_tickets_are_false_not_exceptions(ticket: str | None) -> None:
    assert verify_ticket(ticket, "run-abc", SECRET) is False


def test_no_secret_means_no_ticket_is_valid() -> None:
    """With no key configured the consumer stays open on its own; a ticket is
    never the thing that opens it."""
    assert not verify_ticket(mint_ticket("run-abc", SECRET), "run-abc", "")
