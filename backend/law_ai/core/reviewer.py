"""Reviewer identity for HITL decisions (BL-20260811-04, spec 036 T-003).

Every human-in-the-loop decision in this repo — quarantine approve/reject,
LSAT proposal approve/reject — used to be attributed by a **free-text**
string the caller supplied. That is fine for a CLI operator typing
``--reviewer alice`` and useless as an audit record: an API client could
claim to be anyone, and there was no join back to a real account.

Now that Django accounts exist (spec 036 T-002 / BL-20260503-13), this
module is the one place that answers "who is deciding?":

* **A signed-in caller wins over the body.** When the request carries a real
  Django user (session cookie, or an ``ApiToken`` bound to a user), the
  reviewer name is that user's username and the claimed free-text value is
  ignored — a client cannot dress up as someone else.
* **The free-text path survives.** With no user (env-key dev mode, the
  management command, an unauthenticated local instance) the caller's
  claimed string is used exactly as before, and ``user_id`` stays ``None``.
  Constitution §5 gates are unchanged; only the attribution improves.

``attributed()`` publishes the resolved identity on a context variable so
deep audit writers (``lsat.services.proposals._log_decision``) can stamp the
account id without every intermediate function growing a parameter. It is a
context manager with an explicit reset so an identity cannot leak onto the
next request handled by the same worker thread.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

#: What a decision is recorded under when nobody identified themselves.
UNATTRIBUTED = "(unattributed)"


@dataclass(frozen=True)
class ReviewerIdentity:
    """Who made a HITL decision, in both the legacy and the account form."""

    #: Display/legacy attribution string persisted on the row.
    name: str
    #: Primary key of the Django user, when the caller is a real account.
    user_id: int | None = None
    #: The Django user object itself, for FK assignment. Never serialised.
    user: Any | None = None

    @property
    def is_account(self) -> bool:
        """True when the attribution is backed by a real user account."""
        return self.user_id is not None

    def audit_fields(self) -> dict[str, Any]:
        """The attribution fields every decision event carries (§4)."""
        name = (self.name or "").strip()
        return {
            "reviewer": (
                name if name and name.lower() != "anonymous" else UNATTRIBUTED
            ),
            "reviewer_user_id": self.user_id,
        }


#: The anonymous identity — a decision with no account and no claimed name.
ANONYMOUS = ReviewerIdentity(name="anonymous")

_CURRENT: contextvars.ContextVar[ReviewerIdentity] = contextvars.ContextVar(
    "law_ai_current_reviewer", default=ANONYMOUS
)


def reviewer_from_user(user: Any) -> ReviewerIdentity:
    """Build an identity from a Django user, or ANONYMOUS when there is none."""
    if user is None:
        return ANONYMOUS
    pk = getattr(user, "pk", None)
    if pk is None or not isinstance(pk, int):
        return ANONYMOUS
    name = (
        getattr(user, "get_username", lambda: "")()
        or getattr(user, "username", "")
        or f"user:{pk}"
    )
    return ReviewerIdentity(name=str(name), user_id=pk, user=user)


def reviewer_from_request(
    request: Any, *, claimed: str | None = None
) -> ReviewerIdentity:
    """Resolve the reviewer for ``request``.

    The signed-in account always wins; ``claimed`` (a free-text body field)
    is only honoured when there is no account to attribute the decision to.
    """
    from law_ai.core.auth import is_signed_in

    if request is not None and is_signed_in(request):
        identity = reviewer_from_user(getattr(request, "user", None))
        if identity.is_account:
            return identity
    text = (claimed or "").strip()
    return ReviewerIdentity(name=text or "anonymous")


def current_reviewer() -> ReviewerIdentity:
    """The identity published by the innermost enclosing :func:`attributed`."""
    return _CURRENT.get()


@contextmanager
def attributed(identity: ReviewerIdentity) -> Iterator[ReviewerIdentity]:
    """Publish ``identity`` for the duration of the block, then restore."""
    token = _CURRENT.set(identity)
    try:
        yield identity
    finally:
        _CURRENT.reset(token)


__all__ = [
    "ANONYMOUS",
    "UNATTRIBUTED",
    "ReviewerIdentity",
    "attributed",
    "current_reviewer",
    "reviewer_from_request",
    "reviewer_from_user",
]
