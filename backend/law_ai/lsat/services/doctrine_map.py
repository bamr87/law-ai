"""Doctrine gap → study plan (BL-20260817-04).

The platform has two halves that never met. On one side a matter carries
*issue tags* — "negligence", "statutory-interpretation" — describing the legal
question someone is actually working. On the other, the LSAT lab holds a
concept catalog, a knowledge library and a question bank keyed by *reasoning*
concepts. A learner working a negligence matter had no way to be told that
their weak spot is causation-vs-correlation, and the library had no way to
know which of its 50-odd concepts mattered to them this week.

This module is the bridge, and it is deliberately **static, curated data**
(``law_ai/lsat/data/doctrine_concept_map.json``) rather than an inferred or
model-generated mapping:

* it is reviewable — a human can read the whole file and disagree with a row;
* it cannot drift or hallucinate between runs, so a study plan is reproducible;
* an unknown concept id is a hard error at load time (same discipline as
  ``factory/taxonomy.py``), so a typo fails loudly instead of quietly
  recommending nothing.

Ranking is the learner's own gap, not the map's order: concepts they have
never practised come first, then the ones they get wrong most often. The
matter supplies *relevance*; :mod:`law_ai.lsat.services.attempts` supplies
*need*.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Curated map, next to the module rather than inside the LSAT content data
#: directory: it describes matters, not questions.
DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "doctrine_concept_map.json"
)

#: How many drills a plan suggests per concept.
DRILLS_PER_CONCEPT = 3


class DoctrineMapError(ValueError):
    """The curated map references something the concept catalog does not have."""


@lru_cache(maxsize=1)
def load_doctrine_map() -> dict[str, dict[str, Any]]:
    """Load and validate the issue-tag → concept map.

    Validation is the point of the function: every concept id must exist in
    ``load_concepts()``. A stale row would otherwise show up as a study plan
    that silently recommends nothing.
    """
    from law_ai.lsat.services.bank import load_concepts

    if not DATA_PATH.is_file():  # pragma: no cover - packaging accident
        raise DoctrineMapError(f"doctrine map missing at {DATA_PATH}")
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    entries = raw.get("map") or {}
    if not isinstance(entries, dict) or not entries:
        raise DoctrineMapError("doctrine map has no entries")

    known = set(load_concepts())
    out: dict[str, dict[str, Any]] = {}
    for tag, entry in entries.items():
        concepts = list(entry.get("concepts") or [])
        if not concepts:
            raise DoctrineMapError(f"issue tag {tag!r} maps to no concepts")
        unknown = [c for c in concepts if c not in known]
        if unknown:
            raise DoctrineMapError(
                f"issue tag {tag!r} maps to unknown concept(s): {', '.join(unknown)}"
            )
        out[str(tag)] = {
            "label": str(entry.get("label") or tag),
            "why": str(entry.get("why") or ""),
            "concepts": concepts,
        }
    return out


def normalise_tag(tag: str) -> str:
    """Issue tags arrive from humans; compare them case- and space-insensitively."""
    return "-".join(str(tag).strip().lower().replace("_", "-").split())


def concepts_for_tags(tags: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Concepts the given issue tags call for, plus the tags nothing covers.

    Returns ``(refs, unmapped)`` where each ref carries the concept and the
    tags that asked for it — a concept two issues both need is worth more of
    the learner's time, and the response says why it was recommended.
    """
    mapping = load_doctrine_map()
    by_concept: dict[str, dict[str, Any]] = {}
    unmapped: list[str] = []
    for raw_tag in tags:
        tag = normalise_tag(raw_tag)
        entry = mapping.get(tag)
        if entry is None:
            if tag and tag not in unmapped:
                unmapped.append(tag)
            continue
        for concept_id in entry["concepts"]:
            ref = by_concept.setdefault(
                concept_id,
                {"concept_id": concept_id, "from_tags": [], "why": entry["why"]},
            )
            if tag not in ref["from_tags"]:
                ref["from_tags"].append(tag)
    return list(by_concept.values()), unmapped


def _learner_gaps(user: Any) -> dict[str, dict[str, Any]]:
    """Per-concept accuracy for one learner, or ``{}`` when there is none."""
    if user is None:
        return {}
    try:
        from law_ai.lsat.models import LsatAttempt
    except Exception:  # pragma: no cover - app not installed
        return {}
    gaps: dict[str, dict[str, Any]] = {}
    rows = LsatAttempt.objects.filter(user=user).values("concepts", "correct")
    for row in rows:
        for concept_id in row["concepts"] or []:
            bucket = gaps.setdefault(str(concept_id), {"attempts": 0, "correct": 0})
            bucket["attempts"] += 1
            if row["correct"]:
                bucket["correct"] += 1
    for bucket in gaps.values():
        bucket["accuracy"] = round(bucket["correct"] / bucket["attempts"], 4)
    return gaps


def _drills_for(concept_id: str, limit: int = DRILLS_PER_CONCEPT) -> list[str]:
    """Bank question ids tagged with this concept (stable order)."""
    from law_ai.lsat.services.bank import load_bank

    try:
        bank = load_bank()
    except Exception:  # pragma: no cover - content dir missing
        return []
    return sorted(q.id for q in bank.values() if concept_id in q.concepts)[:limit]


def _articles_for(concept_id: str) -> list[str]:
    from law_ai.lsat.services.library import articles_teaching

    try:
        return articles_teaching(concept_id)
    except Exception:  # pragma: no cover - library not present
        return []


def recommend_for_tags(
    tags: list[str], *, user: Any = None, limit: int = 10
) -> dict[str, Any]:
    """Rank the concepts these issue tags call for by the learner's gap."""
    refs, unmapped = concepts_for_tags(tags)
    from law_ai.lsat.services.bank import load_concepts

    catalog = load_concepts()
    gaps = _learner_gaps(user)

    recommendations: list[dict[str, Any]] = []
    for ref in refs:
        concept = catalog.get(ref["concept_id"])
        gap = gaps.get(ref["concept_id"])
        attempts = int(gap["attempts"]) if gap else 0
        accuracy = float(gap["accuracy"]) if gap else None
        recommendations.append(
            {
                "concept_id": ref["concept_id"],
                "name": concept.name if concept else ref["concept_id"],
                "sections": list(concept.sections) if concept else [],
                "summary": concept.summary if concept else "",
                "from_tags": ref["from_tags"],
                "why": ref["why"],
                "attempts": attempts,
                "accuracy": accuracy,
                # A concept the learner has never touched is the biggest gap
                # there is, so it sorts ahead of anything they merely do badly.
                "status": (
                    "unpractised"
                    if attempts == 0
                    else ("weak" if (accuracy or 0) < 0.7 else "solid")
                ),
                "articles": _articles_for(ref["concept_id"]),
                "drills": _drills_for(ref["concept_id"]),
            }
        )

    def _rank(item: dict[str, Any]) -> tuple[int, float, int, str]:
        never = 0 if item["attempts"] == 0 else 1
        accuracy = item["accuracy"] if item["accuracy"] is not None else 0.0
        # More issue tags asking for the same concept breaks ties upward.
        return (never, accuracy, -len(item["from_tags"]), item["concept_id"])

    recommendations.sort(key=_rank)
    return {
        "concepts": recommendations[:limit],
        "unmapped_tags": unmapped,
        "covered_tags": sorted(
            {tag for r in refs for tag in r["from_tags"]},
        ),
    }


def study_plan_for_matter(
    matter: Any, *, user: Any = None, limit: int = 10
) -> dict[str, Any]:
    """The matter-shaped wrapper the API returns."""
    plan = recommend_for_tags(
        list(getattr(matter, "issue_tags", []) or []), user=user, limit=limit
    )
    plan["matter"] = {
        "slug": getattr(matter, "slug", ""),
        "name": getattr(matter, "name", ""),
        "issue_tags": list(getattr(matter, "issue_tags", []) or []),
    }
    return plan


__all__ = [
    "DATA_PATH",
    "DoctrineMapError",
    "concepts_for_tags",
    "load_doctrine_map",
    "normalise_tag",
    "recommend_for_tags",
    "study_plan_for_matter",
]
