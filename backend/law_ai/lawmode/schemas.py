"""Finding and report schemas for the lawmode review (spec 057 FR-1).

Ported from ``lawmode/lawmode/models.py``. The field names and the severity
values are unchanged, so a report still reads the way the lawmode CLI and its
VS Code extension expect. What changed is what the report is allowed to say:

* ``has_blocking_risks`` is gone. The old tree used it to fail a merge on the
  model's say-so; here no automated verdict blocks or passes a change
  (constitution §5). Each finding carries a :class:`ReviewStatus` instead, and
  :attr:`ReviewResult.human_approval_required` says whether a person has to
  look. ``unparsed_findings`` counts what the model returned and this code
  could not read, so an incomplete report cannot pass for a clean one.
* ``auto_fix_patch`` is gone: nothing ever wrote it, and a model-authored patch
  is exactly the unreviewed change the HITL gate exists to stop.
* every report carries the not-legal-advice notice, and timestamps are
  timezone-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, computed_field

#: The one-line form of ``disclaimer.md``, carried on every serialised report
#: so a finding is never read without it (spec 057 §2, R-2).
DISCLAIMER_NOTICE = (
    "Not legal advice. lawmode findings are automated, advisory legal-risk "
    "analysis: they may be wrong or incomplete, and a review with no findings "
    "is not a statement that the code is compliant. Consult qualified legal "
    "counsel."
)


class Severity(StrEnum):
    """Risk severity levels."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ReviewStatus(StrEnum):
    """Where a finding stands with the human-in-the-loop gate.

    None of these is a verdict on the code. ``not_required`` means the policy
    asks only for a comment at that severity. ``unreviewed`` means the policy
    asks for a human and none has decided yet. ``awaiting_review`` means the
    finding is sitting in the review queue; it is set only by the code that
    actually enqueues it (the ``lawmode_finding`` queue, spec 057 FR-5), so a
    report never claims a queue item that does not exist.
    """

    NOT_REQUIRED = "not_required"
    AWAITING_REVIEW = "awaiting_review"
    UNREVIEWED = "unreviewed"


def _risk_id() -> str:
    return f"R{uuid4().hex[:8].upper()}"


class Risk(BaseModel):
    """A legal risk identified in code.

    ``law`` names the authority or licence the finding relies on and
    ``jurisdiction`` where it applies; ``citation`` is a link to it when the
    model gave a usable one.

    >>> risk = Risk(
    ...     severity=Severity.HIGH,
    ...     title="Personal data sent unencrypted",
    ...     law="GDPR Art. 32",
    ...     description="An email address is posted over plain HTTP.",
    ...     mitigation="Send it over TLS.",
    ... )
    >>> risk.review_status.value
    'unreviewed'
    """

    id: str = Field(default_factory=_risk_id)
    severity: Severity
    title: str
    law: str  # e.g., "GDPR Art. 32"
    jurisdiction: str | None = None  # e.g., "EU"
    citation: HttpUrl | None = None
    description: str
    mitigation: str
    line_start: int | None = None
    line_end: int | None = None
    file_path: str | None = None
    code_snippet: str | None = None
    #: Defaults to the cautious reading: a finding nobody has run through the
    #: policy is treated as needing a human, never as cleared.
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED


class ReviewResult(BaseModel):
    """Complete legal review result.

    >>> review = ReviewResult(jurisdictions=["US", "EU"])
    >>> review.has_critical_risks(), review.human_approval_required
    (False, False)
    """

    review_id: UUID = Field(default_factory=uuid4)
    commit_sha: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    jurisdictions: list[str] = Field(default_factory=list)
    domain: str | None = None
    risks: list[Risk] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)  # Review steps that ran
    signature: str | None = None  # Optional PGP signature
    metadata: dict[str, Any] = Field(default_factory=dict)
    #: Findings the model returned that could not be read into a
    #: :class:`Risk`. They are not in ``risks``, so a report that has any is
    #: incomplete: it asks for a human and never reads as "no findings".
    unparsed_findings: int = Field(default=0, ge=0)
    disclaimer: str = DISCLAIMER_NOTICE

    def has_critical_risks(self) -> bool:
        """Check if review contains critical risks.

        >>> ReviewResult().has_critical_risks()
        False
        """
        return any(risk.severity == Severity.CRITICAL for risk in self.risks)

    def risks_requiring_review(self) -> list[Risk]:
        """The findings a human has to decide on, in report order.

        >>> ReviewResult().risks_requiring_review()
        []
        """
        return [
            risk
            for risk in self.risks
            if risk.review_status != ReviewStatus.NOT_REQUIRED
        ]

    # mypy rejects any decorator stacked on @property; this is pydantic's own
    # documented way to serialise one.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def human_approval_required(self) -> bool:
        """True when a human has to look at this report.

        That is the case when any finding is waiting on a human, and when the
        model returned findings that could not be read — a finding this code
        failed to parse is not one it may wave through. Serialised with the
        report, so every consumer sees it.

        This is the only "outcome" a report has. It is deliberately not a
        pass/fail: ``False`` means no finding reached a gated severity, not
        that the code is fine.

        >>> ReviewResult().human_approval_required
        False
        >>> ReviewResult(unparsed_findings=1).human_approval_required
        True
        """
        return bool(self.risks_requiring_review()) or self.unparsed_findings > 0
