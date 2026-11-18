"""The ``lawmode_finding`` review queue (spec 057 FR-5, AC-3).

A finding the policy gates — critical, high, or one that does not name its
authority — becomes one ``PendingReview`` row of kind ``lawmode_finding``,
the same queue that holds quarantined cases and statutes (spec 015). That row
is where a human decides on the finding. Nothing here passes or fails a
change, and nothing about a finding is ever written to the knowledge graph:
``lawmode_finding`` is a decision-only kind, so approving one records the
decision and stops (``ingestionapp.services.approval``).

The ``code_legal_review`` graph's HITL node calls :func:`queue_finding` and
marks the finding ``awaiting_review`` only once the row exists, so a report
never claims a queue item that is not there.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from law_ai.ingestionapp.quarantine_kinds import KIND_LAWMODE_FINDING
from law_ai.lawmode.schemas import DISCLAIMER_NOTICE, ReviewStatus, Risk

#: ``PendingReview.source`` for every lawmode row.
SOURCE = "lawmode"


def queue_id(review_id: str, risk_id: str) -> str:
    """The queue row id for one finding of one review.

    Stable for a given review and finding, so queuing the same finding twice
    updates its row instead of adding a second one.

    >>> queue_id("6f1c", "R002")
    'lawmode:6f1c:R002'
    """
    return f"{SOURCE}:{review_id}:{risk_id}"


def queue_reason(risk: Risk, *, gated_because: str) -> str:
    """The one-line ``reason`` a reviewer reads in the queue list.

    >>> risk = Risk(severity="High", title="Email sent over HTTP", law="GDPR Art. 32",
    ...             jurisdiction="EU", description="d", mitigation="m", chain="privacy")
    >>> queue_reason(risk, gated_because="severity")
    'lawmode High finding (privacy): Email sent over HTTP — GDPR Art. 32 [EU]; gated by severity. Advisory: a human decides.'
    """
    where = risk.jurisdiction or "no jurisdiction given"
    text = (
        f"lawmode {risk.severity.value} finding ({risk.chain or 'review'}): "
        f"{risk.title} — {risk.law} [{where}]; gated by {gated_because}. "
        "Advisory: a human decides."
    )
    return " ".join(text.split())


def queue_finding(
    risk: Risk,
    *,
    review_id: str,
    gated_because: str,
    context: Mapping[str, Any],
) -> str:
    """Put one gated finding in the review queue and return its row id.

    ``context`` is what a reviewer needs to trace the finding to the calls
    that produced it — the chain, the serving model, the prompt id and
    version, the file, the commit and the SHA-256 of the code (never the
    code). The stored finding is marked ``awaiting_review``, because that is
    what it is once this row exists.

    ``confidence`` is ``0.0``: a finding has no extraction score, and the
    ``reason`` column says why the row is in the queue instead.
    """
    from law_ai.ingestionapp.models import PendingReview

    pk = queue_id(review_id, risk.id)
    queued = risk.model_copy(update={"review_status": ReviewStatus.AWAITING_REVIEW})
    PendingReview.objects.update_or_create(
        id=pk,
        defaults={
            "source": SOURCE,
            "kind": KIND_LAWMODE_FINDING,
            "payload": {
                **context,
                "id": pk,
                "source": SOURCE,
                "kind": KIND_LAWMODE_FINDING,
                "review_id": review_id,
                "gated_because": gated_because,
                "finding": queued.model_dump(mode="json"),
                # The authority was named by the model; no research tool has
                # checked it (spec 057 P3 is where that changes).
                "citations_verified": False,
                "disclaimer": DISCLAIMER_NOTICE,
            },
            "confidence": 0.0,
            "reason": queue_reason(risk, gated_because=gated_because),
        },
    )
    return pk
