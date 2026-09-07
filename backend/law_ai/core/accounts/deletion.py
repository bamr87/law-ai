"""Account deletion that respects the audit trail (BL-20260817-01, half two).

"Delete my account" and "keep an immutable audit log" pull in opposite
directions, and the naive resolution — ``user.delete()`` — is wrong in both:
it cascades away rows the constitution says are permanent (§4), and it is
blocked outright by the ``PROTECT`` FK on :class:`~law_ai.matters.models.Matter`
so it fails halfway through, leaving an account partly dismantled.

The path implemented here separates the two kinds of data an account holds:

* **Personal data the user owns** — LSAT attempt history, their per-user
  setting rows — is genuinely removed.
* **Records of what happened** — audit events, HITL decisions, quarantine
  reviews, analyses — is kept and *de-identified*: the auth row survives with
  its username scrubbed to ``deleted-user-<pk>``, no usable password, and
  ``is_active=False``, so every FK stays valid and no history is rewritten.

Matters are soft-archived (§5) and their ``PROTECT`` ownership is reassigned
to a tombstone account, so the deletion cannot be blocked by them and a later
genuine purge (a retention job, not this function) has a single owner to work
from. Their slugs are rewritten on the way over — ``Matter`` is unique on
``(owner, slug)`` and slugs are auto-derived from the matter's name, so
without that the *second* account to delete a matter called "Lease" would
collide on the shared tombstone and roll the whole de-identification back.
Every step is counted and logged as one ``account.deleted`` provenance event.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("law_ai.core.accounts")

#: Username of the account archived matters are reassigned to. Created on
#: demand, never logged in to (unusable password, inactive).
TOMBSTONE_USERNAME = "deleted-user"


def tombstone_user() -> Any:
    """The sentinel owner for data outliving the account that made it."""
    from django.contrib.auth import get_user_model

    model = get_user_model()
    user, created = model.objects.get_or_create(
        username=TOMBSTONE_USERNAME,
        defaults={"is_active": False},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


#: ``Matter.slug`` is a CharField(max_length=64); the rewritten tombstone slug
#: has to fit in it.
_SLUG_MAX = 64


def _tombstone_slug(matter: Any, taken: set[str]) -> str:
    """A slug that is unique *on the tombstone account*.

    ``Matter`` carries an unconditional ``UniqueConstraint(owner, slug)`` and
    slugs are only unique per owner — they are auto-derived from the matter's
    name, so "lease", "divorce" and "eviction" collide between accounts as a
    matter of course. Reassigning every deleted account's matters to the one
    shared tombstone therefore made the *second* deletion of a colliding slug
    raise ``IntegrityError``, and since the whole of :func:`delete_account`
    runs in one ``transaction.atomic()`` block that rolled back the entire
    de-identification: the account stayed live, its tokens stayed valid, and
    the endpoint 500'd.

    Suffixing the matter's own pk fixes it and stays readable. The pk is
    globally unique and contains no ``-``, so ``<slug>-<pk>`` is injective and
    the original slug is still recoverable by a human reading the row. ``taken``
    guards the one case suffixing cannot: truncation to fit ``max_length``.
    """
    import secrets

    base = str(matter.slug or "matter")
    suffix = f"-{matter.pk}"
    candidate = base[: _SLUG_MAX - len(suffix)] + suffix
    while candidate in taken:  # pragma: no cover - only reachable via truncation
        suffix = f"-{secrets.token_hex(4)}"
        candidate = base[: _SLUG_MAX - len(suffix)] + suffix
    return candidate


def _archive_matters(user: Any, tombstone: Any, now: datetime) -> int:
    try:
        from law_ai.matters.models import Matter
    except Exception:  # pragma: no cover - app not installed
        return 0
    rows = list(Matter.objects.filter(owner=user))
    if not rows:
        return 0
    taken = set(Matter.objects.filter(owner=tombstone).values_list("slug", flat=True))
    for matter in rows:
        if matter.archived_at is None:
            matter.archived_at = now
        matter.owner = tombstone
        matter.slug = _tombstone_slug(matter, taken)
        taken.add(matter.slug)
        matter.save(update_fields=["archived_at", "owner", "slug"])
    return len(rows)


def _archive_analyses(user: Any, now: datetime) -> int:
    try:
        from law_ai.analysis.models import AnalysisRun, ShareLink
    except Exception:  # pragma: no cover - app not installed
        return 0
    runs = AnalysisRun.objects.filter(created_by=user, archived_at__isnull=True)
    count = runs.count()
    # Revoke first: an archived run whose slug still resolved would be a
    # deleted account's data still readable on the open internet.
    ShareLink.objects.filter(analysis__created_by=user, revoked_at__isnull=True).update(
        revoked_at=now
    )
    runs.update(archived_at=now)
    return count


def _revoke_tokens(user: Any, now: datetime) -> int:
    from law_ai.core.models import ApiToken

    return int(
        ApiToken.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=now
        )
    )


def _purge_personal(user: Any) -> dict[str, int]:
    """Hard-delete the rows that are the user's own data, not a record."""
    out: dict[str, int] = {}
    try:
        from law_ai.lsat.models import LsatAttempt

        out["lsat_attempts"] = int(LsatAttempt.objects.filter(user=user).delete()[0])
    except Exception:  # pragma: no cover - app not installed
        out["lsat_attempts"] = 0
    try:
        from law_ai.core.models import SettingValue

        out["settings"] = int(
            SettingValue.objects.filter(
                scope_type=SettingValue.SCOPE_USER, scope_id=f"user:{user.pk}"
            ).delete()[0]
        )
    except Exception:  # pragma: no cover - table missing
        out["settings"] = 0
    return out


def delete_account(user: Any, *, reason: str = "") -> dict[str, Any]:
    """De-identify ``user`` and release everything the account holds.

    Returns a summary of what happened. Idempotent: running it again on an
    already-deleted account is a no-op that reports zeros.
    """
    from django.db import transaction

    from law_ai.core.provenance import provenance

    now = datetime.now(UTC)
    original_username = user.get_username()
    if original_username.startswith("deleted-user"):
        return {"already_deleted": True, "username": original_username}

    with transaction.atomic():
        tombstone = tombstone_user()
        summary: dict[str, Any] = {
            "user_id": user.pk,
            "matters_archived": _archive_matters(user, tombstone, now),
            "analyses_archived": _archive_analyses(user, now),
            "tokens_revoked": _revoke_tokens(user, now),
        }
        summary.update(_purge_personal(user))

        # De-identify rather than delete: every audit row, HITL decision and
        # quarantine review keeps a valid FK, and nothing in the history is
        # rewritten (§4).
        user.username = f"deleted-user-{user.pk}"
        user.email = ""
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.set_unusable_password()
        user.save()

    summary["deleted_at"] = now.isoformat()
    summary["username"] = user.username
    provenance.log_event(
        "account.deleted",
        {**summary, "reason": (reason or "")[:500]},
    )
    logger.info("account %s de-identified: %s", original_username, summary)
    return summary


__all__ = ["TOMBSTONE_USERNAME", "delete_account", "tombstone_user"]
