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

    # Decide, with attribution + rationale (constitution §4). `--reviewer-user`
    # binds the decision to a real Django account (BL-20260906-20).
    python manage.py review_queue approve <id> --reviewer-user alice --note "ok"
    python manage.py review_queue reject  <id> --reviewer alice --note "duplicate"

    # Approve a whole scoped batch — e.g. every PDF-derived CRS title-18
    # section a bulk import penalised into the queue (BL-20260905-98).
    python manage.py review_queue approve-all --id-prefix us-co/crs/18- \
        --reviewer-user alice --note "spot-checked the import"

    # Re-run today's extractor over the stored raw document (no commit).
    python manage.py review_queue re-extract <id> --reviewer alice

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
            choices=[
                "list",
                "show",
                "approve",
                "approve-all",
                "reject",
                "re-extract",
                "commit",
            ],
        )
        parser.add_argument("review_id", nargs="?", default=None)
        parser.add_argument("--reviewer", default="", help="Who is deciding.")
        parser.add_argument(
            "--reviewer-user",
            default="",
            help=(
                "Username of the deciding account (BL-20260906-20). Recorded as "
                "a real FK so the decision is joinable, unlike --reviewer."
            ),
        )
        parser.add_argument("--note", default="", help="Why (recorded in audit).")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument(
            "--source", default="", help="Filter for `approve-all` (exact match)."
        )
        parser.add_argument(
            "--kind", default="", help="Filter for `approve-all` (exact match)."
        )
        parser.add_argument(
            "--id-prefix",
            default="",
            help="Filter for `approve-all`: id starts with this (e.g. a CRS title).",
        )
        parser.add_argument(
            "--state",
            choices=["pending", "approved", "rejected", "awaiting-commit", "all"],
            default="pending",
            help="Filter for `list` (default: pending).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        from law_ai.ingestionapp.models import PendingReview

        action = opts["action"]
        reviewer_user = self._resolve_user(opts["reviewer_user"])
        if action == "list":
            self._list(PendingReview, opts["state"], opts["limit"])
            return
        if action == "commit":
            self._commit_all(opts["limit"])
            return
        if action == "approve-all":
            self._approve_all(
                PendingReview,
                opts,
                reviewer=opts["reviewer"],
                reviewer_user=reviewer_user,
            )
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
        elif action == "re-extract":
            self._reextract(review, reviewer=opts["reviewer"])
        elif action in ("approve", "reject"):
            self._decide(
                review,
                approved=action == "approve",
                reviewer=opts["reviewer"],
                reviewer_user=reviewer_user,
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

    def _resolve_user(self, username: str) -> Any:
        """Resolve ``--reviewer-user`` to a Django account (BL-20260906-20).

        The CLI could only ever record a free-text ``--reviewer``, which is not
        joinable to anything; the admin path already stores the FK. An unknown
        username is an error rather than a silent downgrade to free text — a
        typo must not quietly cost the attribution.
        """
        if not username:
            return None
        from django.contrib.auth import get_user_model

        model = get_user_model()
        try:
            return model.objects.get(**{model.USERNAME_FIELD: username})
        except model.DoesNotExist as exc:
            raise CommandError(f"no user account named {username!r}") from exc

    def _decide(
        self,
        review: Any,
        *,
        approved: bool,
        reviewer: str,
        note: str,
        reviewer_user: Any = None,
    ) -> None:
        from law_ai.ingestionapp.services.approval import (
            commit_approved_review,
            record_decision,
        )

        if not reviewer and reviewer_user is None:
            self.stdout.write(
                self.style.WARNING(
                    "no --reviewer or --reviewer-user given; the decision will "
                    "be recorded as unattributed (constitution §4 prefers a name)"
                )
            )
        record_decision(
            review,
            approved=approved,
            reviewer=reviewer,
            reviewer_user=reviewer_user,
            note=note,
        )
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

    def _reextract(self, review: Any, *, reviewer: str) -> None:
        """Re-run the extractor over the stored raw document (BL-20260503-10)."""
        from law_ai.ingestionapp.services.approval import (
            ApprovalError,
            reextract_review,
        )

        try:
            outcome = reextract_review(review, reviewer=reviewer)
        except ApprovalError as exc:
            raise CommandError(str(exc)) from exc
        if not outcome.get("reextracted"):
            detail = outcome.get("error") or outcome.get("skipped") or outcome
            self.stdout.write(self.style.ERROR(f"not re-extracted: {detail}"))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"re-extracted {review.pk}: "
                f"{outcome['previous_confidence']:.3f} -> "
                f"{outcome['confidence']:.3f} "
                f"({outcome['n_citations']} citation(s))"
            )
        )
        if outcome.get("clears_threshold"):
            self.stdout.write(
                "now clears the confidence threshold — "
                "`approve` it to commit (approval is still the HITL gate)"
            )

    def _approve_all(
        self, model: Any, opts: dict[str, Any], *, reviewer: str, reviewer_user: Any
    ) -> None:
        """Approve + commit a scoped batch of pending rows (BL-20260905-98).

        A bulk import — notably the PDF fallback, whose sections are penalised
        into the queue by design — can put hundreds of rows in front of a
        reviewer who has already satisfied themselves about the whole title.
        Approving them one id at a time is the only thing standing in the way,
        so this applies one decision across a scope.

        At least one of ``--source`` / ``--kind`` / ``--id-prefix`` is
        required: "approve everything pending" is never what a reviewer means,
        and constitution §5 keeps the human in the loop, not out of it.
        """
        from law_ai.ingestionapp.services.approval import (
            commit_approved_review,
            record_decision,
        )

        source, kind, prefix = opts["source"], opts["kind"], opts["id_prefix"]
        if not (source or kind or prefix):
            raise CommandError(
                "approve-all needs a scope: pass --source, --kind or --id-prefix"
            )
        qs = model.objects.filter(approved__isnull=True, committed_at__isnull=True)
        if source:
            qs = qs.filter(source=source)
        if kind:
            qs = qs.filter(kind=kind)
        if prefix:
            qs = qs.filter(id__startswith=prefix)

        rows = list(qs.order_by("created_at")[: opts["limit"]])
        if not rows:
            self.stdout.write("no pending rows match that scope")
            return
        if not reviewer and reviewer_user is None:
            self.stdout.write(
                self.style.WARNING(
                    "no --reviewer or --reviewer-user given; every decision in "
                    "this batch will be recorded as unattributed"
                )
            )

        committed = 0
        failures: list[tuple[str, str]] = []
        for review in rows:
            record_decision(
                review,
                approved=True,
                reviewer=reviewer,
                reviewer_user=reviewer_user,
                note=opts["note"],
            )
            outcome = async_to_sync(commit_approved_review)(review)
            if outcome.get("committed"):
                committed += 1
            else:
                failures.append((str(review.pk), str(outcome.get("error") or outcome)))
        self.stdout.write(
            self.style.SUCCESS(f"approved {len(rows)} row(s), committed {committed}")
        )
        for pk, error in failures:
            self.stdout.write(self.style.ERROR(f"  {pk}: {error}"))

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
