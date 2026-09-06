"""Constitution §13 attribution: who said this, where, and when (BL-20260803-04).

§13 requires every statement of law to name its issuing authority. Prose is
not mechanically checkable — an LLM can always slip an unattributed sentence
past a regex — so the deterministic contract this module enforces is
*per citation*: a citation an agent emits must carry a court, a jurisdiction,
a decision date, and a binding/persuasive classification, or the output is
pinned for human review.

The data exists upstream: ``GraphRAGRetriever`` passages already carry
``court``, ``decided_at`` and ``source_url`` straight off the ``:Case`` node.
This module backfills a citation's attribution *from the passage it cites*
rather than trusting the model to restate it — a model-restated court is one
more thing that can be hallucinated.

Binding vs persuasive is a heuristic over the graph's own jurisdiction
encoding: the retriever filters by ``toLower(court) STARTS WITH <prefix>``, so
a court code is a jurisdiction path. A citation is ``binding`` when its court
sits under the requested jurisdiction, ``persuasive`` when it does not, and
``unknown`` when either side is missing — never a guess (§13 "absence is
reported").
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

AuthorityKind = Literal["binding", "persuasive", "unknown"]
OpinionPart = Literal["majority", "dissent", "concurrence", "unknown"]


class Attribution(BaseModel):
    """Issuing authority for one cited proposition."""

    court: str | None = Field(
        default=None, description="Court code as stored on the :Case node."
    )
    jurisdiction: str | None = Field(
        default=None,
        description="Jurisdiction the court sits in, derived from the court code.",
    )
    decided_at: str | None = Field(
        default=None, description="Decision date (ISO) from the graph."
    )
    authority: AuthorityKind = Field(
        default="unknown",
        description=(
            "`binding` when the court is within the requested jurisdiction, "
            "`persuasive` when it is elsewhere, `unknown` when either is absent."
        ),
    )
    opinion_part: OpinionPart = Field(
        default="unknown",
        description="Majority/dissent/concurrence when the graph records it.",
    )

    @property
    def complete(self) -> bool:
        """True when court + jurisdiction + date are all present (§13 minimum)."""
        return bool(self.court and self.jurisdiction and self.decided_at)


def jurisdiction_of(court: str | None) -> str | None:
    """Jurisdiction path for a court code, or ``None`` when unknown.

    Court codes in this graph are hierarchical, dash-separated
    (``us-supreme``, ``us-ca-9``): the leading segment is the sovereign and
    the rest narrows the court. The jurisdiction is everything but the final
    narrowing segment when there is more than one, and the whole code when
    there is not — enough to compare two courts, never a claim the graph does
    not support.
    """
    code = str(court or "").strip().lower()
    if not code:
        return None
    parts = [p for p in code.split("-") if p]
    if len(parts) <= 1:
        return "-".join(parts) or None
    return "-".join(parts[:-1])


def classify_authority(
    court: str | None, requested_jurisdiction: str | None
) -> AuthorityKind:
    """Binding when the court sits under the requested jurisdiction.

    Returns ``unknown`` — never a guess — when either side is missing, which
    is the common case today: most questions arrive without a jurisdiction.
    """
    code = str(court or "").strip().lower()
    wanted = str(requested_jurisdiction or "").strip().lower()
    if not code or not wanted:
        return "unknown"
    if code == wanted or code.startswith(f"{wanted}-"):
        return "binding"
    return "persuasive"


def attribution_from_passage(
    passage: Mapping[str, Any] | None, requested_jurisdiction: str | None = None
) -> Attribution:
    """Build an :class:`Attribution` from one retrieved passage."""
    if not passage:
        return Attribution()
    court = str(passage.get("court") or "").strip() or None
    decided_at = str(passage.get("decided_at") or "").strip() or None
    jurisdiction = (
        str(passage.get("jurisdiction_code") or "").strip() or None
    ) or jurisdiction_of(court)
    part = str(passage.get("opinion_part") or "").strip().lower()
    opinion_part: OpinionPart = (
        part  # type: ignore[assignment]
        if part in ("majority", "dissent", "concurrence")
        else "unknown"
    )
    return Attribution(
        court=court,
        jurisdiction=jurisdiction,
        decided_at=decided_at,
        authority=classify_authority(court, requested_jurisdiction),
        opinion_part=opinion_part,
    )


def match_passage(
    citation: Mapping[str, Any], passages: Iterable[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """Find the retrieved passage a citation refers to.

    ``source_url`` first (the model copies it verbatim from the prompt), then
    a case-insensitive title match. No fuzzy scoring: a wrong match would
    attach one case's court to another case's proposition, which is worse than
    reporting the attribution as absent.
    """
    url = str(citation.get("source_url") or "").strip()
    text = str(citation.get("text") or "").strip().casefold()
    by_url = None
    for passage in passages:
        p_url = str(passage.get("source_url") or "").strip()
        if url and p_url and url == p_url:
            by_url = passage
            break
    if by_url is not None:
        return by_url
    if not text:
        return None
    for passage in passages:
        title = str(passage.get("title") or "").strip().casefold()
        if title and (title in text or text in title):
            return passage
    return None


def check_attribution(citations: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return one human-readable problem per under-attributed citation.

    An empty list means every citation names court, jurisdiction and date.
    The caller decides what to do with a non-empty list; in this codebase it
    forces ``human_approval_required``.
    """
    problems: list[str] = []
    for index, citation in enumerate(citations):
        label = str(citation.get("text") or "").strip() or f"citation #{index + 1}"
        raw = citation.get("attribution")
        if not isinstance(raw, Mapping):
            problems.append(f"{label}: no attribution recorded")
            continue
        attribution = Attribution.model_validate(dict(raw))
        missing = [
            field
            for field, value in (
                ("court", attribution.court),
                ("jurisdiction", attribution.jurisdiction),
                ("decided_at", attribution.decided_at),
            )
            if not value
        ]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
    return problems


__all__ = [
    "Attribution",
    "AuthorityKind",
    "OpinionPart",
    "attribution_from_passage",
    "check_attribution",
    "classify_authority",
    "jurisdiction_of",
    "match_passage",
]
