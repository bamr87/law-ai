"""``manage.py seed_review_queue`` — put a known row in the HITL queue.

The browser end-to-end spec for the admin approval flow (spec 051 /
BL-20260503-17) needs one uncommitted :class:`PendingReview` to approve, and it
must be the *same* row on every run or the assertion "this case reached the
graph" has nothing to name. Nothing in the repo could create one: real rows
come from an ingestion run, which needs a live source.

The payload is a minimal CourtListener-shaped opinion, so
``IngestionScout.extract`` (rule-based + eyecite, no model call) produces a
deterministic ``:Case`` node with two citations.

Idempotent by construction — ``--reset`` puts an already-approved row back into
the pending state so the spec can run again without a database wipe::

    python manage.py seed_review_queue --reset

Never enabled outside the e2e stack by accident: it writes exactly one row with
an obvious ``e2e-`` id, and ``--reset`` is the only way it touches an existing
one.
"""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

#: Stable id the e2e spec looks for. Prefixed so it can never be mistaken for
#: a real quarantine row in a shared database.
REVIEW_ID = "e2e-hitl-review"

#: The graph node the approval must produce.
CASE_ID = "e2e-hitl-case"

PAYLOAD: dict[str, Any] = {
    "id": CASE_ID,
    "case_name": "E2E Harness v. Quarantine Queue",
    "absolute_url": "/opinion/e2e-hitl-case/e2e-harness-v-quarantine-queue/",
    "cluster": {"court": "Test Court of Appeals", "date_filed": "2026-01-15"},
    "plain_text": (
        "This opinion exists so the human-in-the-loop approval flow can be "
        "exercised end to end. The panel follows Marbury v. Madison, 5 U.S. "
        "137 (1803), and distinguishes Roe v. Wade, 410 U.S. 113 (1973), on "
        "the ground that neither concerned an automated test fixture."
    ),
}


class Command(BaseCommand):
    help = "Seed one deterministic PendingReview row for the e2e admin flow."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Return an existing row to the pending, uncommitted state.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from law_ai.ingestionapp.models import PendingReview

        review, created = PendingReview.objects.get_or_create(
            id=REVIEW_ID,
            defaults={
                "source": "e2e",
                "kind": "case",
                "payload": PAYLOAD,
                # Below the 0.85 auto-commit threshold, which is why a human
                # has to look at it.
                "confidence": 0.42,
                "reason": "seeded for the e2e admin HITL spec (BL-20260503-17)",
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"seed_review_queue: created {REVIEW_ID}")
            )
            return

        if not options.get("reset"):
            state = "committed" if review.committed_at else "pending"
            self.stdout.write(f"seed_review_queue: {REVIEW_ID} exists ({state})")
            return

        review.payload = PAYLOAD
        review.confidence = 0.42
        review.approved = None
        review.reviewed_at = None
        review.reviewer = ""
        review.review_note = ""
        review.committed_at = None
        review.commit_error = ""
        review.save()
        self.stdout.write(self.style.SUCCESS(f"seed_review_queue: reset {REVIEW_ID}"))
