"""Operate the HITL quarantine queue from the CLI (spec 029).

The Django admin was the only review surface, and approving there used to do
nothing (BL-20260810-03). This gives operators a scriptable equivalent with
reviewer attribution.

Examples::

    # What is waiting?
    python manage.py review_queue list
    python manage.py review_queue list --state awaiting-commit

    # Why was this quarantined? (full payload + reason)
    python manage.py review_queue show <id>

    # Decide, with attribution + rationale (constitution §4).
    python manage.py review_queue approve <id> --reviewer alice --note "verified"
    python manage.py review_queue reject  <id> --reviewer alice --note "duplicate"

    # Commit everything a human already approved.
    python manage.py review_queue commit --limit 50
"""

from __future__ import annotations

import json
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Inspect and action the ingestion HITL quarantine queue."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "action",
            choices=["list", "show", "approve", "reject", "commit"],
        )
        parser.add_argument("review_id", nargs="?", default=None)
        parser.add_argument("--reviewer", default="", help="Who is deciding.")
        parser.add_argument("--note", default="", help="Why (recorded in audit).")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument(
            "--state",
            choices=["pending", "approved", "rejected", "awaiting-commit", "all"],
            default="pending",
            help="Filter for `list` (default: pending).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        from law_ai.ingestionapp.models import PendingReview

        action = opts["action"]
        if action == "list":
            self._list(PendingReview, opts["state"], opts["limit"])
            return
        if action == "commit":
            self._commit_all(opts["limit"])
            return

        review_id = opts["review_id"]
        if not review_id:
            raise CommandError(f"'{action}' requires a review id")
        try:
            review = PendingReview.objects.get(pk=review_id)
        except PendingReview.DoesNotExist as exc:
            raise CommandError(f"no PendingReview with id {review_id!r}") from exc

        if action == "show":
            self._show(review)
        elif action in ("approve", "reject"):
            self._decide(
                review,
                approved=action == "approve",
                reviewer=opts["reviewer"],
                note=opts["note"],
            )

    # -- actions -------------------------------------------------------

    def _list(self, model: Any, state: str, limit: int) -> None:
        qs = model.objects.all()
        if state == "pending":
            qs = qs.filter(approved__isnull=True)
        elif state == "approved":
            qs = qs.filter(approved=True)
        elif state == "rejected":
            qs = qs.filter(approved=False)
        elif state == "awaiting-commit":
            qs = qs.filter(approved=True, committed_at__isnull=True)

        rows = list(qs.order_by("created_at")[:limit])
        if not rows:
            self.stdout.write(f"no rows in state={state}")
            return
        self.stdout.write(f"{'id':<28} {'source':<18} {'conf':>5}  state")
        for r in rows:
            if r.committed_at:
                st = "committed"
            elif r.approved is True:
                st = "approved (awaiting commit)"
            elif r.approved is False:
                st = "rejected"
            else:
                st = "pending review"
            if r.commit_error:
                st += f" [error: {r.commit_error[:40]}]"
            self.stdout.write(
                f"{str(r.pk)[:27]:<28} {r.source[:17]:<18} {r.confidence:>5.2f}  {st}"
            )
        self.stdout.write(f"\n{len(rows)} row(s), state={state}")

    def _show(self, review: Any) -> None:
        """Print WHY this was quarantined plus the full payload."""
        self.stdout.write(f"id:         {review.pk}")
        self.stdout.write(f"source:     {review.source}")
        self.stdout.write(f"kind:       {review.kind}")
        self.stdout.write(f"confidence: {review.confidence}")
        self.stdout.write(f"reason:     {review.reason or '(none recorded)'}")
        self.stdout.write(f"created:    {review.created_at}")
        self.stdout.write(f"reviewed:   {review.reviewed_at or '(not reviewed)'}")
        self.stdout.write(f"reviewer:   {review.reviewer or '(unattributed)'}")
        self.stdout.write(f"note:       {review.review_note or '(none)'}")
        self.stdout.write(f"committed:  {review.committed_at or '(not committed)'}")
        if review.commit_error:
            self.stdout.write(self.style.ERROR(f"commit_error: {review.commit_error}"))
        self.stdout.write("\npayload:")
        self.stdout.write(json.dumps(review.payload, indent=2, default=str)[:4000])

    def _decide(self, review: Any, *, approved: bool, reviewer: str, note: str) -> None:
        from law_ai.ingestionapp.services.approval import (
            commit_approved_review,
            record_decision,
        )

        if not reviewer:
            self.stdout.write(
                self.style.WARNING(
                    "no --reviewer given; the decision will be recorded as "
                    "unattributed (constitution §4 prefers a name)"
                )
            )
        record_decision(review, approved=approved, reviewer=reviewer, note=note)
        if not approved:
            self.stdout.write(self.style.SUCCESS(f"rejected {review.pk}"))
            return

        outcome = async_to_sync(commit_approved_review)(review)
        if outcome.get("committed"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"approved + committed {review.pk} "
                    f"({outcome.get('edges', 0)} citation edge(s))"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"approved but NOT committed: {outcome.get('error') or outcome}"
                )
            )

    def _commit_all(self, limit: int) -> None:
        from law_ai.ingestionapp.services.approval import commit_approved_reviews

        results = commit_approved_reviews(limit)
        if not results:
            self.stdout.write("nothing awaiting commit")
            return
        committed = sum(1 for r in results if r.get("committed"))
        failed = [r for r in results if r.get("error")]
        self.stdout.write(
            self.style.SUCCESS(f"committed {committed}/{len(results)} approved row(s)")
        )
        for r in failed:
            self.stdout.write(self.style.ERROR(f"  {r['id']}: {r['error']}"))
