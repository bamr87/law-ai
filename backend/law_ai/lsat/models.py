"""LSAT ORM models (BL-20260527-05).

The proposal store began as an append-only JSONL log replayed on every read
(:mod:`law_ai.lsat.services.proposals`), which is honest and auditable but
linear: every ``list_proposals`` call re-parses the whole tail, and the tail
itself is capped, so a long-lived queue eventually loses its oldest rows from
the replay.

:class:`LsatProposal` is the indexed mirror of that log. The JSONL file stays
the audit trail and the source of truth for replay — every event is still
appended there first — while this table carries the *current* state of each
proposal for reads. ``payload`` holds the replayed row verbatim, so the API
shape does not depend on which store answered; the scalar columns exist to be
filtered and ordered on.

Writes are best-effort (see ``proposals._mirror_row``): a database that is
absent, unmigrated, or unreachable degrades back to the JSONL replay rather
than blocking a reviewer.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class LsatProposal(models.Model):
    """Current state of one HITL proposal; ``payload`` is the replayed row."""

    id = models.CharField(primary_key=True, max_length=64)
    proposal_kind = models.CharField(max_length=32, default="question", db_index=True)
    status = models.CharField(max_length=16, default="pending", db_index=True)
    section = models.CharField(max_length=8, blank=True, default="")
    difficulty = models.CharField(max_length=16, blank=True, default="")
    agent_trace_id = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    confidence = models.FloatField(default=0.0)
    reviewer = models.CharField(max_length=128, blank=True, default="", db_index=True)
    note = models.TextField(blank=True, default="")
    question_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"LsatProposal({self.id}, {self.proposal_kind}, {self.status})"


class LsatAttempt(models.Model):
    """One graded LSAT answer by a signed-in learner (BL-20260503-05).

    Grading has always written an ``lsat_grade`` row to the JSONL audit log,
    which is a *global* stream: ``/api/lsat/stats`` could only ever report
    "everyone on this instance, all time". With accounts (spec 036 T-002)
    there is finally a learner to attribute an attempt to, so per-learner
    accuracy and a spaced-repetition queue become answerable.

    The audit event is unchanged and still written for every attempt,
    signed-in or not — this table is an *addition*, not a replacement, and an
    anonymous learner's experience is byte-identical to before.

    ``on_delete=CASCADE``: study history is the learner's own data, not an
    audit record, so deleting an account takes it with them (the anonymised
    ``lsat_grade`` audit rows remain, per constitution §4).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lsat_attempts",
    )
    question_id = models.CharField(max_length=64, db_index=True)
    section = models.CharField(max_length=8, blank=True, default="", db_index=True)
    difficulty = models.CharField(max_length=16, blank=True, default="")
    choice = models.CharField(max_length=4, blank=True, default="")
    correct = models.BooleanField(default=False)
    hints_used = models.IntegerField(default=0)
    shuffled = models.BooleanField(default=False)
    concepts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "question_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        verdict = "correct" if self.correct else "wrong"
        return f"LsatAttempt({self.user_id}, {self.question_id}, {verdict})"

    @property
    def assisted(self) -> bool:
        """True when the learner opened a hint before answering."""
        return bool(self.hints_used)


class LsatWritingAttempt(models.Model):
    """One evaluated Argumentative Writing response by a signed-in learner.

    BL-20260906-18. :class:`LsatAttempt` records graded multiple choice only,
    so writing practice lived in the JSONL audit log alone — an *instance-wide*
    stream. ``/api/lsat/stats`` could therefore report a signed-in learner's
    drill accuracy and, right beside it, everyone-on-this-box's essay bands,
    which is the wrong number under the right label.

    A sibling table rather than a ``section="WS"`` row on ``LsatAttempt``: an
    essay has no ``choice`` and no ``correct``, and the writing section is
    **unscored** — a band is a study instrument produced by a model, not a key.
    Forcing it into the graded-answer shape would put it in the accuracy
    denominator and in the spaced-repetition queue, where it does not belong.

    The ``lsat_writing_evaluate`` audit event is unchanged and still written
    for every evaluation, signed-in or not; this table is an addition. Bands
    are machine-derived, so ``model`` and ``prompt_version`` ride along to be
    shown at the point of display (NFR-PROV-1).

    ``on_delete=CASCADE``, like ``LsatAttempt``: study history is the
    learner's own data (constitution §4 keeps the anonymised audit rows).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lsat_writing_attempts",
    )
    prompt_id = models.CharField(max_length=64, db_index=True)
    rubric_id = models.CharField(max_length=64, blank=True, default="")
    #: The rubric's weighted band. Nullable because a degraded evaluation (no
    #: provider reachable) still happened and must not be recorded as a zero.
    weighted_band = models.FloatField(null=True, blank=True)
    #: Per-criterion bands, ``{criterion_id: band}`` — criterion-level progress
    #: without a second schema change.
    criteria = models.JSONField(default=dict, blank=True)
    response_chars = models.IntegerField(default=0)
    model = models.CharField(max_length=128, blank=True, default="")
    prompt_version = models.CharField(max_length=128, blank=True, default="")
    degraded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"LsatWritingAttempt({self.user_id}, {self.prompt_id})"


class LsatArticleRead(models.Model):
    """Current read state of one library article for one reader (BL-20260905-39).

    Reading progress was reconstructed on every request by replaying
    ``lsat_article_read`` events out of the JSONL audit tail. That tail is a
    bounded ring: once a deployment's log rotates past a read event the article
    silently un-marks itself server-side, and the learner sees *less* progress
    than they have. The client's ``localStorage`` union hid it locally, so a
    fresh browser was the first place the loss became visible.

    Same relationship to the log that :class:`LsatProposal` has: every event is
    still appended to the JSONL first — that remains the audit trail — and this
    table carries the *current* state for reads. It never rotates, so it is the
    authoritative half where the two disagree.

    ``reader`` is the string :func:`law_ai.lsat.urls._reader_id` produces
    (``"user:<pk>"`` or ``"instance"``), not a foreign key: an anonymous
    deployment-wide reader has no row in the user table to point at.

    Never hard-deleted (constitution §4): un-marking an article writes
    ``read=False``, which is also what makes the row a *state* rather than a
    second, lossy copy of the event stream.
    """

    reader = models.CharField(max_length=64, db_index=True)
    article_id = models.CharField(max_length=64, db_index=True)
    read = models.BooleanField(default=True)
    #: Denormalised from the article at write time so a section rollup does not
    #: need the library loaded; the library stays the source of truth.
    sections = models.JSONField(default=list, blank=True)
    kind = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["reader", "article_id"],
                name="lsat_article_read_unique_reader_article",
            )
        ]
        indexes = [
            models.Index(fields=["reader", "read"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        verdict = "read" if self.read else "unread"
        return f"LsatArticleRead({self.reader}, {self.article_id}, {verdict})"
