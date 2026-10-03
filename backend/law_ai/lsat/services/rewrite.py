"""Judge every bank item; rewrite the ones the judge objects to (spec 054 FR-11).

The bank grew through agents and hand authoring, and the judge tier could
only ever say what was wrong with a *draft*. This module points the same
adversarial judge at questions already in the bank and, when it objects,
runs ``LSATQuestionEditor`` through the gates → judge → revise loop to fix
them, then hands the rewrite to Fable for a final review and files it as a
pending ``rewrite`` proposal. A human promotes it **in place**
(:func:`~law_ai.lsat.services.proposals.promote_rewrite`), so the question
keeps its id, its stamp, its lineage and its learners' history.

A clean verdict files nothing — the item is fine and the verdict is cached
per prompt version so a sweep can resume without re-billing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from law_ai.lsat.services import llm_cache
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import Question, load_bank, load_concepts
from law_ai.lsat.services.contrast import contrast_set, final_review, stimulus_of
from law_ai.lsat.services.playbooks import classify

logger = logging.getLogger("law_ai.lsat.rewrite")

#: Response-cache kind for the judge's verdict on a bank item as it stands.
JUDGE_CACHE_KIND = "bank_judge"
REWRITE_KIND = "rewrite"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def validate_rewrite(draft: dict[str, Any], source: Question) -> list[str]:
    """Every deterministic reason a rewrite must not reach a reviewer.

    A rewrite must stay the same question: same section, still reads as the
    stamped type, five distinct choices, known concepts, a change summary —
    and, when siblings share the stimulus, the stimulus verbatim.

    >>> validate_rewrite({}, load_bank()["lr-002"])[0]
    'stem is missing'
    """
    issues: list[str] = []
    stem = str(draft.get("stem") or "")
    if not stem.strip():
        return ["stem is missing"]
    if str(draft.get("section") or source.section) != source.section:
        issues.append("section must not change")
    if len(contrast_set(source.id)) > 1 and _norm(stimulus_of(stem)) != _norm(
        stimulus_of(source.stem)
    ):
        issues.append(
            "this question shares its stimulus with a contrast set; the stimulus "
            "must be kept verbatim"
        )
    choices = draft.get("choices") or []
    labels = [str(c.get("label")) for c in choices if isinstance(c, dict)]
    if labels != ["A", "B", "C", "D", "E"]:
        return [*issues, "choices must be labelled A-E in order"]
    texts = {str(c["label"]): str(c.get("text") or "") for c in choices}
    if any(not t.strip() for t in texts.values()):
        issues.append("every choice needs text")
    if len({_norm(t) for t in texts.values()}) < 5:
        issues.append("two choices are identical")
    correct = str(draft.get("correct") or "")
    if correct not in texts:
        issues.append("correct must name one of the choices")
    if source.archetype:
        probe = Question.model_validate(
            {
                "id": f"{source.id}-probe",
                "section": source.section,
                "difficulty": source.difficulty,
                "stem": stem,
                "choices": [
                    {"label": lab, "text": texts.get(lab) or "x"} for lab in "ABCDE"
                ],
                "correct": correct if correct in texts else "A",
                "explanation": "probe",
                "source": "probe",
                "concepts": [str(c) for c in draft.get("concepts") or []],
            }
        )
        read = classify(probe).archetype_id
        if read != source.archetype:
            issues.append(
                f"the rewritten stem reads as {read or 'no recognised type'}, not "
                f"{source.archetype}; the question must keep its type"
            )
    catalog = load_concepts()
    unknown = [c for c in (draft.get("concepts") or []) if str(c) not in catalog]
    if unknown:
        issues.append(f"unknown concept ids: {unknown}")
    if not str(draft.get("explanation") or "").strip():
        issues.append("explanation is missing")
    if len(str(draft.get("change_summary") or "").strip()) < 20:
        issues.append("change_summary must say what changed and why")
    return issues


class ReviewResult(BaseModel):
    """What :func:`review_question` did, for the API and the sweep."""

    question_id: str
    #: The judge's verdict on the item as it stands.
    verdict: str | None = None
    issues: list[str] = Field(default_factory=list)
    #: True when the judge had no objection and nothing was drafted.
    clean: bool = False
    proposal_id: str | None = None
    accepted: bool = False
    final_verdict: str | None = None
    rounds: int = 0
    degraded: bool = False
    cached: bool = False
    model: str = "fallback/offline"


async def judge_bank_item(
    q: Question, *, refresh: bool = False
) -> tuple[dict[str, Any], bool]:
    """The judge's verdict on ``q`` as it stands, cached per prompt version.

    Returns ``(verdict, cached)``. A degraded verdict is never cached.
    """
    from law_ai.agents_runtime.crews.lsat_draft_judge import (
        PROMPT_VERSION,
        LSATDraftJudge,
    )

    key = llm_cache.cache_key(
        JUDGE_CACHE_KIND, {"question_id": q.id, "prompt_version": PROMPT_VERSION}
    )
    if not refresh:
        hit = llm_cache.get(key)
        if isinstance(hit, dict) and isinstance(hit.get("verdict"), dict):
            return dict(hit["verdict"]), True
    out = await LSATDraftJudge().run(
        {
            "draft": {**q.model_dump(), "correct": q.correct},
            "passage_id": q.passage_id,
            "proposal_id": None,
        }
    )
    verdict = out.verdict.model_dump()
    if not verdict.get("degraded"):
        llm_cache.put(key, {"question_id": q.id, "verdict": verdict})
    return verdict, False


def judge_objects(verdict: dict[str, Any]) -> bool:
    """Whether a bank item's verdict is worth a rewrite.

    ``fail`` and a disagreeing blind key always are; a ``flag`` is when it
    names concrete issues. A degraded verdict is never an objection.
    """
    from law_ai.lsat.factory.revise import judge_objections

    if verdict.get("degraded"):
        return False
    if verdict.get("verdict") == "fail" or verdict.get("key_agrees") is False:
        return True
    return verdict.get("verdict") == "flag" and bool(judge_objections(verdict))


async def review_question(
    question_id: str,
    *,
    max_rounds: int = 3,
    refresh: bool = False,
    use_final_review: bool = True,
) -> ReviewResult:
    """Judge one bank item and, if it objects, rewrite it through the loop.

    Files a pending ``rewrite`` proposal carrying the edited item, the
    original verdict (``meta.original_judge``), every round
    (``meta.revisions``) and the final review (``meta.final_review``). A clean
    item files nothing; a degraded judge or editor files nothing either.
    """
    from law_ai.agents_runtime.crews.lsat_draft_judge import LSATDraftJudge
    from law_ai.agents_runtime.crews.lsat_question_editor import LSATQuestionEditor
    from law_ai.lsat.factory.revise import author_with_review, judge_objections

    source = load_bank()[question_id]
    verdict, cached = await judge_bank_item(source, refresh=refresh)
    result = ReviewResult(
        question_id=question_id,
        verdict=str(verdict.get("verdict")),
        issues=judge_objections(verdict),
        cached=cached,
        model=str(verdict.get("model") or "fallback/offline"),
        degraded=bool(verdict.get("degraded")),
    )
    if result.degraded:
        return result
    if not judge_objects(verdict):
        result.clean = True
        return result

    editor = LSATQuestionEditor()
    judge = LSATDraftJudge()

    async def _author(critique: list[str]) -> tuple[dict[str, Any] | None, str, bool]:
        # The first round fixes the original verdict; later rounds fix that
        # plus whatever the loop objected to.
        out = await editor.run(
            {"question_id": question_id, "critique": critique or result.issues}
        )
        if out.draft is not None:
            return out.draft.model_dump(), out.model, out.degraded
        if out.degraded or not out.issues:
            return None, out.model, True
        return {"_invalid": list(out.issues)}, out.model, False

    def _gates(draft: dict[str, Any]) -> list[str]:
        invalid = draft.get("_invalid")
        if isinstance(invalid, list):
            return [f"draft was malformed: {i}" for i in invalid]
        return validate_rewrite(draft, source)

    async def _judge(draft: dict[str, Any]) -> dict[str, Any]:
        out = await judge.run(
            {"draft": draft, "passage_id": source.passage_id, "proposal_id": None}
        )
        return out.verdict.model_dump()

    async def _final(draft: dict[str, Any]) -> dict[str, Any]:
        return await final_review(draft, passage_id=source.passage_id)

    outcome = await author_with_review(
        _author,
        _gates,
        _judge,
        max_rounds=max_rounds,
        final_reviewer=_final if use_final_review else None,
    )
    result.rounds = len(outcome.rounds)
    result.accepted = outcome.accepted
    result.model = outcome.model
    if outcome.final_review is not None:
        result.final_verdict = str(outcome.final_review.get("verdict"))
    if outcome.draft is None or "_invalid" in outcome.draft:
        result.degraded = outcome.degraded
        return result
    draft = dict(outcome.draft)
    meta: dict[str, Any] = {
        "rewrite_of": question_id,
        "original_judge": verdict,
        "revisions": {
            "accepted": outcome.accepted,
            "rounds": [r.model_dump() for r in outcome.rounds],
        },
        "factory": {
            "archetype_id": source.archetype,
            "executor": "LSATQuestionEditor",
            "mode": "rewrite",
        },
    }
    if outcome.judge is not None:
        meta["factory"]["judge"] = outcome.judge
    if outcome.final_review is not None:
        meta["final_review"] = outcome.final_review
    result.proposal_id = proposals_store.record_proposal(
        draft,
        agent_trace_id="",
        model=outcome.model,
        confidence=float(draft.get("confidence") or 0.0),
        source_concept_ids=[str(c) for c in draft.get("concepts") or []],
        meta=meta,
        proposal_kind=REWRITE_KIND,
    )
    return result


def pending_rewrite_ids() -> set[str]:
    """Question ids with a rewrite already waiting in the queue."""
    out: set[str] = set()
    for row in proposals_store.list_proposals("pending", limit=1000):
        if row.get("proposal_kind") != REWRITE_KIND:
            continue
        qid = (row.get("draft") or {}).get("question_id")
        if isinstance(qid, str):
            out.add(qid)
    return out


def judged_question_ids() -> set[str]:
    """Question ids whose current verdict is cached."""
    return {
        str(row["question_id"])
        for row in llm_cache.entries(JUDGE_CACHE_KIND)
        if isinstance(row.get("question_id"), str)
    }


__all__ = [
    "JUDGE_CACHE_KIND",
    "REWRITE_KIND",
    "ReviewResult",
    "judge_bank_item",
    "judge_objects",
    "judged_question_ids",
    "pending_rewrite_ids",
    "review_question",
    "validate_rewrite",
]
