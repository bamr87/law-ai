"""The lawmode review service — one legal-risk review of source code.

Ported from ``lawmode/lawmode/core.py`` (``LawModeAgent.review_code``), spec
057 FR-1/FR-2. The shape is the same — code in, a :class:`ReviewResult` out —
and four things are different on purpose:

* **One provider path.** The model call goes through ``law_ai.core.llm``, so it
  runs on ``LLM_PROVIDER_CHAIN`` and writes the chain's ``llm_call`` provenance
  event. There is no lawmode provider client and no model name in this module;
  the only model input is the validated ``LAWMODE_MODELS`` setting. Each review
  — finished or failed — also writes an ``agent_call`` event and a
  ``lawmode_review`` event that names the review, the file, the commit and a
  SHA-256 of the code. The code itself is never logged.
* **The prompt is a versioned file**, ``prompts/lawmode/review.v1.md``, sent as
  the system instruction with its id and version on the call. The code under
  review travels as the user turn, as data.
* **A failed review is an error, never a report.** The old agent turned a
  failed run into a fabricated "High" finding and guessed a finding out of any
  unparseable reply that contained the word "risk". Here an unavailable chain
  raises :class:`ReviewUnavailableError` and an unusable reply raises
  :class:`ReviewParseError`, so "could not run" can never read as findings — or
  as none. A reply that is readable but has entries that are not (an unknown
  severity, no title) still produces a report, and that report says it is
  incomplete and asks for a human.
* **No verdict.** Findings at a gated severity are marked for a human
  (:class:`~law_ai.lawmode.schemas.ReviewStatus`); nothing here passes or
  fails a change, and ``ENABLE_HUMAN_APPROVAL_GATES`` is not consulted because
  switching the gates off must not clear a finding (spec 057 NFR-HITL-1).

This is the single-call path of phase P1. The eight-chain ``code_legal_review``
graph and the ``lawmode_finding`` review queue build on it in later phases.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, ValidationError

from law_ai.core import llm
from law_ai.core.provenance import provenance
from law_ai.lawmode import policy as lawmode_policy
from law_ai.lawmode.policy import PolicyConfig
from law_ai.lawmode.schemas import ReviewResult, ReviewStatus, Risk, Severity

logger = logging.getLogger("law_ai.lawmode.review")

#: Caller name on the chain's ``llm_call`` provenance event.
AGENT = "lawmode_review"
PROMPT_ID = "lawmode.review"
PROMPT_VERSION = "v1"
PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "agents_runtime"
    / "prompts"
    / "lawmode"
    / "review.v1.md"
)

#: Type of the structured provenance event written once per review.
REVIEW_EVENT = "lawmode_review"

#: What ``law`` says when the model named no authority. A legal proposition
#: with no issuing authority is not passed off as one (constitution §13): the
#: finding is kept, labelled, and sent to a human whatever its severity.
UNATTRIBUTED_LAW = "No authority cited by the model"

#: Replies that fill a field without answering it.
_NON_ANSWERS = frozenset(
    {
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "unspecified",
        "not applicable",
        "tbd",
        "various",
        "law",
        "laws",
        "the law",
        "legislation",
        "regulation",
        "regulations",
    }
)
#: "applicable privacy regulations", "relevant data protection law": a class of
#: law, not an authority. This is a floor against the obvious non-answers, not
#: verification — nothing in this phase checks that a named authority exists.
_VAGUE_AUTHORITY = re.compile(
    r"^(?:the\s+)?(?:applicable|relevant|various|unknown|unspecified)\b",
    re.IGNORECASE,
)

_SEVERITY_BY_NAME = {severity.value.lower(): severity for severity in Severity}
_URL = TypeAdapter(HttpUrl)
_AUDIT_TEXT_CHARS = 200

_REVIEW_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "jurisdictions": {"type": "array", "items": {"type": "string"}},
        "domain": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": [severity.value for severity in Severity],
                    },
                    "title": {"type": "string"},
                    "law": {"type": "string"},
                    "jurisdiction": {"type": "string"},
                    "citation": {"type": "string"},
                    "description": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "line_start": {"type": "integer"},
                    "line_end": {"type": "integer"},
                },
                "required": [
                    "severity",
                    "title",
                    "law",
                    "jurisdiction",
                    "description",
                    "mitigation",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["jurisdictions", "risks"],
    "additionalProperties": False,
}


class ReviewError(RuntimeError):
    """A review that did not produce a report. Never a clean result.

    ``review_id`` ties the failure to its ``lawmode_review`` provenance event.
    """

    def __init__(self, message: str, *, review_id: str | None = None) -> None:
        super().__init__(message)
        self.review_id = review_id


class ReviewUnavailableError(ReviewError):
    """No provider in the chain could run the review."""


class ReviewParseError(ReviewError):
    """The model answered, but not with a review this service can read."""


class ReviewCodeInput(BaseModel):
    """Input to :meth:`LawmodeReviewer.run`."""

    code: str = Field(min_length=1)
    file_path: str | None = None
    commit_sha: str | None = None


class ParsedReview(BaseModel):
    """What one model reply said, before the policy is applied."""

    jurisdictions: list[str] = Field(default_factory=list)
    domain: str | None = None
    risks: list[Risk] = Field(default_factory=list)
    #: Entries in the reply's ``risks`` array that were not usable findings.
    #: Counted and reported, so a dropped entry is never a silent one.
    unparsed_findings: int = 0


def load_prompt() -> str:
    """The versioned review prompt (``prompts/lawmode/review.v1.md``).

    >>> load_prompt().startswith("# lawmode review")
    True
    """
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _text(value: object) -> str:
    """A model-supplied string, trimmed, with nothing in it that cannot be
    written to a UTF-8 file (JSON can smuggle in a lone surrogate)."""
    if not isinstance(value, str):
        return ""
    return value.encode("utf-8", "replace").decode("utf-8").strip()


def _one_line(value: object) -> str:
    """A model-supplied label on one line.

    A title or an authority that carries its own line breaks could write
    lines of its own into a rendered report; these fields never need them.
    """
    return " ".join(_text(value).split())


def _is_non_answer(text: str) -> bool:
    return text.casefold().strip(" .") in _NON_ANSWERS


def is_unattributed(risk: Risk) -> bool:
    """True when a finding does not say whose law it is, or where it applies.

    >>> is_unattributed(Risk(severity=Severity.LOW, title="t", jurisdiction="EU",
    ...                      law="applicable privacy regulations",
    ...                      description="d", mitigation="m"))
    True
    """
    return (
        risk.law == UNATTRIBUTED_LAW
        or _is_non_answer(risk.law)
        or bool(_VAGUE_AUTHORITY.match(risk.law))
        or not risk.jurisdiction
    )


def _line(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 1 else None


def _citation(value: object) -> HttpUrl | None:
    """A usable link, or nothing. A malformed link must not cost the finding."""
    text = _text(value)
    if not text:
        return None
    try:
        return _URL.validate_python(text)
    except ValidationError:
        return None


def _parse_risk(item: object) -> Risk | None:
    """One entry of the reply's ``risks`` array as a :class:`Risk`, if usable.

    The id, the file path and the review status are never read from the model:
    they are assigned by this service, so a reply cannot mark its own finding
    as reviewed.
    """
    if not isinstance(item, dict):
        return None
    label = _one_line(item.get("severity")).casefold().strip(" .:;,*_`'\"")
    severity = _SEVERITY_BY_NAME.get(label)
    title = _one_line(item.get("title"))
    if severity is None or not title:
        return None
    jurisdiction = _one_line(item.get("jurisdiction"))
    line_start = _line(item.get("line_start"))
    line_end = _line(item.get("line_end"))
    if line_start is None or (line_end is not None and line_end < line_start):
        line_end = None
    return Risk(
        severity=severity,
        title=title,
        law=_one_line(item.get("law")) or UNATTRIBUTED_LAW,
        jurisdiction=None if _is_non_answer(jurisdiction) else jurisdiction or None,
        citation=_citation(item.get("citation")),
        description=_text(item.get("description")),
        mitigation=_text(item.get("mitigation")),
        line_start=line_start,
        line_end=line_end,
    )


def parse_review_reply(raw: str) -> ParsedReview:
    """Read a model reply into findings, jurisdictions and a domain.

    Raises :class:`ReviewParseError` when the reply is not a JSON object with
    a ``risks`` array — an unreadable reply is not "no findings".

    >>> parse_review_reply('{"jurisdictions": ["EU"], "risks": []}').jurisdictions
    ['EU']
    """
    try:
        payload = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ReviewParseError(f"review reply is not JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("risks"), list):
        raise ReviewParseError("review reply has no 'risks' array")

    risks: list[Risk] = []
    unparsed = 0
    for item in payload["risks"]:
        risk = _parse_risk(item)
        if risk is None:
            unparsed += 1
        else:
            risks.append(risk)

    listed = payload.get("jurisdictions")
    jurisdictions: list[str] = []
    for entry in listed if isinstance(listed, list) else []:
        code = _one_line(entry)
        if code and code not in jurisdictions:
            jurisdictions.append(code)

    return ParsedReview(
        jurisdictions=jurisdictions,
        domain=_one_line(payload.get("domain")) or None,
        risks=risks,
        unparsed_findings=unparsed,
    )


def apply_policy(
    risks: list[Risk], policy: PolicyConfig, *, file_path: str | None = None
) -> list[Risk]:
    """Number the findings and mark the ones a human has to decide on.

    A finding is gated when the policy gates its severity, or when it does not
    say whose law it is or where it applies (:func:`is_unattributed`). Gated
    findings are ``unreviewed``: this phase has no review queue to put them
    in, and a report must not claim one.

    >>> risk = Risk(severity=Severity.CRITICAL, title="t", law="GDPR Art. 32",
    ...             jurisdiction="EU", description="d", mitigation="m")
    >>> [(r.id, r.review_status.value) for r in apply_policy([risk], PolicyConfig())]
    [('R001', 'unreviewed')]
    """
    marked: list[Risk] = []
    for number, risk in enumerate(risks, start=1):
        gated = policy.requires_review(risk.severity) or is_unattributed(risk)
        marked.append(
            risk.model_copy(
                update={
                    "id": f"R{number:03d}",
                    "file_path": file_path,
                    "review_status": (
                        ReviewStatus.UNREVIEWED if gated else ReviewStatus.NOT_REQUIRED
                    ),
                }
            )
        )
    return marked


def _user_turn(code: str, *, file_path: str | None, policy: PolicyConfig) -> str:
    """The data envelope for one review: where the code is from, then the code."""
    return (
        f"File: {file_path or '(not given)'}\n"
        f"Jurisdictions to review against when the code names none: "
        f"{', '.join(policy.jurisdictions)}\n"
        f"Declared industry domain: {', '.join(policy.domains) or '(none declared)'}\n\n"
        f"<source_code>\n{code}\n</source_code>\n"
    )


class LawmodeReviewer:
    """Reviews source code for legal risk and returns advisory findings.

    Shaped like this repo's agents — ``run(input) -> structured output``, the
    model call on the provider chain, provenance for every run, and
    ``human_approval_required`` declared because the critical and high
    findings are a human's to decide (spec 057 NFR-HITL-1). It is not
    registered with the agents runtime: the registered agent is the
    ``code_legal_review`` graph of a later phase, which builds on this.

    >>> LawmodeReviewer.human_approval_required
    True
    """

    name = "LawmodeReviewer"
    description = (
        "Reviews source code for legal risk (privacy, licence, security, "
        "accessibility, copyright, sector regulation) and returns advisory "
        "findings, each with the authority the model named for it. Critical "
        "and high findings, and any finding that does not name its authority, "
        "are marked for human review; nothing is passed or failed automatically."
    )
    human_approval_required = True

    def __init__(self, policy: PolicyConfig | None = None) -> None:
        self.policy = policy or lawmode_policy.load_policy()

    async def run(self, input_data: dict[str, Any]) -> ReviewResult:
        """Review ``input_data["code"]``; see :meth:`review_code`."""
        inp = ReviewCodeInput.model_validate(input_data)
        return await self.review_code(
            inp.code, file_path=inp.file_path, commit_sha=inp.commit_sha
        )

    async def review_code(
        self,
        code: str,
        *,
        file_path: str | None = None,
        commit_sha: str | None = None,
    ) -> ReviewResult:
        """Review code and return legal analysis.

        Raises:
            ValueError: ``code`` is empty — there is nothing to review.
            ReviewUnavailableError: no provider in the chain answered.
            ReviewParseError: the reply was not a readable review.
        """
        if not code.strip():
            raise ValueError("no code to review")
        # A bad LAWMODE_MODELS is a configuration error raised before any call
        # is made: there is no review yet to audit.
        models = lawmode_policy.model_overrides()

        review_id = uuid4()
        code_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        # What the audit trail records about the input: a hash, never the code.
        # No random value in here, so the event's input_hash is reproducible.
        audit_input: dict[str, Any] = {
            "code_sha256": code_sha256,
            "code_chars": len(code),
            "file_path": file_path,
            "commit_sha": commit_sha,
            "jurisdictions": list(self.policy.jurisdictions),
        }
        started = time.perf_counter()

        try:
            result = await llm.agenerate(
                _user_turn(code, file_path=file_path, policy=self.policy),
                system=load_prompt(),
                response_schema=_REVIEW_RESPONSE_SCHEMA,
                models=models,
                agent=AGENT,
                prompt_id=PROMPT_ID,
                prompt_version=PROMPT_VERSION,
            )
        except llm.LLMUnavailableError as exc:
            self._record_failure(review_id, audit_input, started, exc)
            raise ReviewUnavailableError(
                f"the lawmode review could not run: {exc}", review_id=str(review_id)
            ) from exc

        try:
            parsed = parse_review_reply(result.text)
            review = ReviewResult(
                review_id=review_id,
                commit_sha=commit_sha,
                jurisdictions=parsed.jurisdictions or list(self.policy.jurisdictions),
                # A declared domain overrides the detected one, as in lawmode's
                # policy file.
                domain=", ".join(self.policy.domains) or parsed.domain,
                risks=apply_policy(parsed.risks, self.policy, file_path=file_path),
                history=[f"{PROMPT_ID}/{PROMPT_VERSION}"],
                unparsed_findings=parsed.unparsed_findings,
            )
        except Exception as exc:
            # The model answered and no report came of it. Whatever went wrong,
            # the attempt is recorded before the error leaves.
            self._record_failure(
                review_id, audit_input, started, exc, model=result.model_label
            )
            if isinstance(exc, ReviewError):
                exc.review_id = str(review_id)
            raise

        trace_id = self._record(
            review_id,
            audit_input,
            started,
            model=result.model_label,
            outcome={
                "findings": len(review.risks),
                "by_severity": {
                    severity.value: sum(
                        1 for risk in review.risks if risk.severity == severity
                    )
                    for severity in Severity
                },
                "requiring_review": len(review.risks_requiring_review()),
                "unparsed_findings": review.unparsed_findings,
                "human_approval_required": review.human_approval_required,
            },
            risks=review.risks,
        )
        review.metadata = {
            "file_path": file_path,
            "code_sha256": code_sha256,
            "model": result.model_label,
            "prompt_id": PROMPT_ID,
            "prompt_version": PROMPT_VERSION,
            "trace_id": trace_id,
            # The authorities come from the model; no research tool checked them.
            "citations_verified": False,
        }
        return review

    def _record_failure(
        self,
        review_id: UUID,
        audit_input: dict[str, Any],
        started: float,
        error: Exception,
        *,
        model: str = "unavailable",
    ) -> None:
        """Record a review that produced no report, so the failure is auditable."""
        logger.info("lawmode review %s did not complete: %s", review_id, error)
        self._record(
            review_id,
            {**audit_input, "error": True},
            started,
            model=model,
            outcome={
                "error_type": type(error).__name__,
                "detail": str(error)[:_AUDIT_TEXT_CHARS],
            },
        )

    def _record(
        self,
        review_id: UUID,
        audit_input: dict[str, Any],
        started: float,
        *,
        model: str,
        outcome: dict[str, Any],
        risks: Sequence[Risk] = (),
    ) -> str:
        """Write the provenance for one review, finished or failed.

        Two events. ``agent_call`` is what every agent in this repo writes; it
        keeps only a hash of its input, so on its own it cannot say which file
        or which code a review was about. ``lawmode_review`` carries those
        fields in the open — the review id, the file, the commit, the SHA-256
        of the code — and the ``trace_id`` that joins the two.
        """
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data=audit_input,
            output_data=outcome,
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            sources=[
                {
                    "law": risk.law[:_AUDIT_TEXT_CHARS],
                    "jurisdiction": (risk.jurisdiction or "")[:_AUDIT_TEXT_CHARS],
                }
                for risk in risks
            ],
            prompt_id=PROMPT_ID,
            prompt_version=PROMPT_VERSION,
        )
        provenance.log_event(
            REVIEW_EVENT,
            {
                "review_id": str(review_id),
                "trace_id": trace_id,
                "agent": self.name,
                "ok": "error" not in audit_input,
                "model": model,
                "prompt_id": PROMPT_ID,
                "prompt_version": PROMPT_VERSION,
                **audit_input,
                **outcome,
            },
        )
        return trace_id
