"""Question-set accuracy review (spec 041 FR-15).

Deterministic integrity sweep over the live bank — the reviewer-facing
half of "review the question set and answers for accuracy": per-question
checks (answer-key sanity in the rationale, concept/passage links, solve-
guide quality), section-level answer-key distribution, and a summary of
every stored AI cross-check verdict (FR-14) so disagreements the chain has
flagged are surfaced next to the deterministic findings. No model calls —
this endpoint is cheap enough to run on demand from the Authoring tab.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from law_ai.lsat.services import llm_cache
from law_ai.lsat.services.bank import (
    load_bank,
    load_concepts,
    load_passages,
)
from law_ai.lsat.services.guides import load_guides, validate_guide_quality
from law_ai.lsat.services.regression import regression_report

_CHOICE_LABELS = ("A", "B", "C", "D", "E")


def _question_issues(section: str | None) -> tuple[list[dict[str, Any]], int]:
    bank = load_bank()
    concepts = load_concepts()
    passages = load_passages()
    guides = load_guides()

    issues: list[dict[str, Any]] = []
    total = 0
    for q in bank.values():
        if section is not None and q.section != section:
            continue
        total += 1
        # The rationale should ground the key: an explanation that never
        # names the correct letter can't be checked by a reviewer at a glance.
        if not re.search(rf"\b{q.correct}\b", q.explanation):
            issues.append(
                {
                    "question_id": q.id,
                    "kind": "explanation_never_names_key",
                    "detail": f"explanation never mentions the answer key {q.correct!r}",
                }
            )
        for cid in q.concepts:
            if cid not in concepts:
                issues.append(
                    {
                        "question_id": q.id,
                        "kind": "unknown_concept",
                        "detail": f"concept {cid!r} is not in the catalog",
                    }
                )
        if q.passage_id is not None and q.passage_id not in passages:
            issues.append(
                {
                    "question_id": q.id,
                    "kind": "broken_passage_link",
                    "detail": f"passage {q.passage_id!r} does not exist",
                }
            )
        guide = guides.get(q.id)
        if guide is not None:
            for problem in validate_guide_quality(guide, q):
                issues.append(
                    {
                        "question_id": q.id,
                        "kind": "guide_quality",
                        "detail": problem,
                    }
                )
    return issues, total


def _distribution(section: str | None) -> dict[str, dict[str, int]]:
    """Answer-key counts per letter, per section (reported, never judged)."""
    out: dict[str, dict[str, int]] = {}
    for q in load_bank().values():
        if section is not None and q.section != section:
            continue
        bucket = out.setdefault(q.section, {label: 0 for label in _CHOICE_LABELS})
        bucket[q.correct] += 1
    return out


def _cross_check_summary(section: str | None) -> dict[str, Any]:
    """Roll up stored FR-14 verdicts: counts + every flagged disagreement."""
    bank = load_bank()
    rows = llm_cache.entries("crosscheck")
    agreements = 0
    disagreements: list[dict[str, Any]] = []
    checked = 0
    for row in rows:
        qid = row.get("question_id")
        q = bank.get(qid) if isinstance(qid, str) else None
        if q is None or (section is not None and q.section != section):
            continue
        checked += 1
        if row.get("agree") is True:
            agreements += 1
        elif row.get("agree") is False:
            disagreements.append(
                {
                    "question_id": qid,
                    "bank_choice": row.get("bank_choice"),
                    "model_choice": row.get("model_choice"),
                    "model": row.get("model"),
                }
            )
    return {
        "checked": checked,
        "agreements": agreements,
        "disagreements": disagreements,
    }


def validate_question_set(section: str | None = None) -> dict[str, Any]:
    """Full accuracy/validation report for the (optionally filtered) bank."""
    issues, total = _question_issues(section)
    guides = load_guides()
    bank = load_bank()
    guide_count = sum(
        1
        for qid in guides
        if section is None or (qid in bank and bank[qid].section == section)
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "section": section,
        "question_count": total,
        "guide_count": guide_count,
        "issue_count": len(issues),
        "issues": issues,
        "answer_distribution": _distribution(section),
        "cross_checks": _cross_check_summary(section),
        # BL-20260527-06: per-item verdict flips over the audit window.
        "regressions": regression_report(section=section),
    }
