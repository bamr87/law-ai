"""Contrast variations — the same stimulus, re-asked as another type (spec 054).

A learner who has just weakened an argument learns most from being asked to
*strengthen the same argument*: the stimulus is unchanged, the task flips,
and the key moves to the mirror image of the one they just found. A
**contrast set** is a root bank question plus every variation stamped
``variation_of`` it, each a different archetype on the same stimulus, each
carrying a ``contrast_note`` that says what changed and why.

This module owns three things:

* the shape — :func:`stimulus_of` splits a stem into the stimulus every
  member must share and the question sentence each member rewrites, and
  :func:`contrast_set` assembles a set from the bank;
* the deterministic gates a drafted variation must clear before a reviewer
  sees it (:func:`validate_variation`) — the stimulus is preserved verbatim,
  the stem reads as the type it claims (the spec 053 classifier decides),
  the key is not the root's key, every named trap exists;
* :func:`draft_variation`, which runs the author → gates → judge → revise
  loop (:mod:`law_ai.lsat.factory.revise`) and files the result as a pending
  ``question`` proposal with its lineage and its revision history. Nothing
  here writes to the bank.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from law_ai.lsat.factory.taxonomy import get_archetype
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import Question, load_bank, load_concepts
from law_ai.lsat.services.playbooks import (
    classify,
    load_playbooks,
    load_traps,
    question_sentence,
)

logger = logging.getLogger("law_ai.lsat.contrast")

#: Shortest contrast note the gates accept: a note that does not say what
#: changed teaches nothing.
MIN_NOTE_CHARS = 60


def stimulus_of(stem: str) -> str:
    """Everything in a stem before its question sentence, or "" when there is none.

    >>> stimulus_of("Premise one.\\n\\nWhich one of the following must be true?")
    'Premise one.'
    >>> stimulus_of("Which one of the following must be true?")
    ''
    """
    parts = [p.strip() for p in re.split(r"\n\s*\n", stem.strip()) if p.strip()]
    return "\n\n".join(parts[:-1]) if len(parts) > 1 else ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def root_id_of(q: Question) -> str:
    """The root of the contrast set ``q`` belongs to (itself when it is one)."""
    return q.variation_of or q.id


def contrast_set(question_id: str) -> list[Question]:
    """The root and every variation of it, root first, then by id.

    Raises ``KeyError`` for an unknown question.

    >>> [q.id for q in contrast_set("lr-002")][0]
    'lr-002'
    """
    bank = load_bank()
    q = bank[question_id]
    root = root_id_of(q)
    members = [m for m in bank.values() if m.id != root and root_id_of(m) == root]
    members.sort(key=lambda m: m.id)
    head = [bank[root]] if root in bank else []
    return head + members


def pivot_targets(q: Question) -> list[str]:
    """Archetypes worth re-asking this stimulus as, most confusable first.

    The playbook's ``confused_with`` list names the types learners swap with
    this one, which is exactly where a side-by-side pair teaches the most;
    the rest of the section follows. Types already present in the set are
    skipped, and passage-bound sections are left alone (their sets are the
    passage's own question stack).
    """
    if q.section != "LR" or q.archetype is None:
        return []
    have = {m.archetype for m in contrast_set(q.id)}
    books = load_playbooks()
    book = books.get(q.archetype)
    preferred = list(book.confused_with) if book else []
    rest = sorted(a for a in books if a.startswith("lr-") and a not in preferred)
    return [a for a in preferred + rest if a not in have and a != q.archetype]


def _check_target(source: Question, target_archetype_id: str) -> list[str]:
    try:
        target = get_archetype(target_archetype_id)
    except KeyError:
        return [f"unknown target archetype {target_archetype_id!r}"]
    issues: list[str] = []
    if target.section != source.section:
        issues.append(
            f"target {target_archetype_id} is a {target.section} type; "
            f"the source is {source.section}"
        )
    if target_archetype_id == source.archetype:
        issues.append("target archetype is the source's own type; nothing to contrast")
    return issues


def _check_stem(stem: str, source: Question) -> list[str]:
    issues: list[str] = []
    src_stimulus = stimulus_of(source.stem)
    if not src_stimulus:
        issues.append("source question has no separable stimulus to preserve")
    elif _norm(stimulus_of(stem)) != _norm(src_stimulus):
        issues.append(
            "stimulus was altered; the variation must keep the source's stimulus "
            "verbatim and rewrite only the question sentence"
        )
    if _norm(question_sentence(stem)) == _norm(question_sentence(source.stem)):
        issues.append("question sentence is unchanged from the source")
    return issues


def _check_choices(
    draft: dict[str, Any], source: Question
) -> tuple[list[str], dict[str, str], str]:
    """Issues, ``{label: text}`` and the stated key (or "" when invalid)."""
    choices = draft.get("choices") or []
    labels = [str(c.get("label")) for c in choices if isinstance(c, dict)]
    if labels != ["A", "B", "C", "D", "E"]:
        return ["choices must be labelled A-E in order"], {}, ""
    texts = {str(c["label"]): str(c.get("text") or "") for c in choices}
    issues: list[str] = []
    if any(not t.strip() for t in texts.values()):
        issues.append("every choice needs text")
    correct = str(draft.get("correct") or "")
    if correct not in texts:
        issues.append("correct must name one of the choices")
        correct = ""
    else:
        src_key_text = next(c.text for c in source.choices if c.label == source.correct)
        if _norm(texts[correct]) == _norm(src_key_text):
            issues.append(
                "the variation's key is the source's key verbatim; a different "
                "task must produce a different credited answer"
            )
    if len({_norm(t) for t in texts.values()}) < 5:
        issues.append("two choices are identical")
    return issues, texts, correct


def _check_reads_as_target(
    draft: dict[str, Any],
    source: Question,
    target_archetype_id: str,
    texts: dict[str, str],
    correct: str,
) -> list[str]:
    probe = Question.model_validate(
        {
            "id": f"{source.id}-probe",
            "section": source.section,
            "difficulty": source.difficulty,
            "stem": str(draft.get("stem") or ""),
            "choices": [
                {"label": lab, "text": texts.get(lab) or "x"} for lab in "ABCDE"
            ],
            "correct": correct or "A",
            "explanation": "probe",
            "source": "probe",
            "concepts": [str(c) for c in draft.get("concepts") or []],
        }
    )
    read = classify(probe)
    if read.archetype_id != target_archetype_id:
        return [
            f"the stem reads as {read.archetype_id or 'no recognised type'}, not "
            f"{target_archetype_id}; use the target type's cue phrasing"
        ]
    return []


def _check_metadata(
    draft: dict[str, Any], target_archetype_id: str, correct: str
) -> list[str]:
    issues: list[str] = []
    target = get_archetype(target_archetype_id)
    catalog = load_concepts()
    concepts = [str(c) for c in draft.get("concepts") or []]
    unknown = [c for c in concepts if c not in catalog]
    if unknown:
        issues.append(f"unknown concept ids: {unknown}")
    if target.concepts[0] not in concepts:
        issues.append(
            f"concepts must include the target's primary tag {target.concepts[0]!r}"
        )
    note = str(draft.get("contrast_note") or "").strip()
    if len(note) < MIN_NOTE_CHARS:
        issues.append(
            "contrast_note must say what changed and why "
            f"(at least {MIN_NOTE_CHARS} characters)"
        )
    traps = load_traps()
    for label, trap in (draft.get("distractor_traps") or {}).items():
        if str(trap) not in traps:
            issues.append(f"distractor_traps[{label}] names unknown trap {trap!r}")
        if str(label) == correct:
            issues.append("distractor_traps must not tag the key")
    if not str(draft.get("explanation") or "").strip():
        issues.append("explanation is missing")
    return issues


def validate_variation(
    draft: dict[str, Any], source: Question, target_archetype_id: str
) -> list[str]:
    """Every deterministic reason a drafted variation must not reach a reviewer.

    Returns an empty list when the draft is clean. The checks are the ones a
    model is likeliest to get wrong and a reviewer likeliest to miss: a
    quietly edited stimulus, a stem that does not actually read as the target
    type, the root's key recycled as the variation's key.

    >>> validate_variation({}, load_bank()["lr-002"], "lr-strengthen")[0]
    'stem is missing'
    """
    issues = _check_target(source, target_archetype_id)
    if issues and issues[0].startswith("unknown target"):
        return issues
    stem = str(draft.get("stem") or "")
    if not stem.strip():
        return ["stem is missing", *issues]
    issues += _check_stem(stem, source)
    choice_issues, texts, correct = _check_choices(draft, source)
    issues += choice_issues
    if not texts:
        return issues
    issues += _check_reads_as_target(draft, source, target_archetype_id, texts, correct)
    issues += _check_metadata(draft, target_archetype_id, correct)
    return issues


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------


def public_contrast_view(
    question_id: str, *, include_spoilers: bool = False
) -> dict[str, Any]:
    """The contrast set as a client sees it: types and tasks, never keys.

    ``contrast_note`` discusses where the keys move, so it is withheld unless
    ``include_spoilers`` — the same soft protection the solve guide uses; the
    client asks for it after grading.
    """
    members = contrast_set(question_id)
    if not members:
        raise KeyError(question_id)
    root = members[0]
    books = load_playbooks()
    out: list[dict[str, Any]] = []
    for m in members:
        book = books.get(m.archetype) if m.archetype else None
        archetype = get_archetype(m.archetype) if m.archetype else None
        entry: dict[str, Any] = {
            "id": m.id,
            "is_root": m.id == root.id,
            "difficulty": m.difficulty,
            "archetype_id": m.archetype,
            "archetype_name": archetype.name if archetype else None,
            "family": book.family if book else None,
            "task": book.task if book else None,
            "question_sentence": question_sentence(m.stem),
        }
        if include_spoilers:
            entry["contrast_note"] = m.contrast_note
        out.append(entry)
    return {
        "root_id": root.id,
        "question_id": question_id,
        "count": len(out),
        "members": out,
        "spoilers": include_spoilers,
    }


# ---------------------------------------------------------------------------
# Drafting through the review loop
# ---------------------------------------------------------------------------


class VariationResult(BaseModel):
    """What :func:`draft_variation` did, for the API and the sweep."""

    source_id: str
    target_archetype_id: str
    proposal_id: str | None = None
    accepted: bool = False
    #: The final reviewer's verdict word, when that stage ran.
    final_verdict: str | None = None
    degraded: bool = False
    rounds: int = 0
    model: str = "fallback/offline"
    issues: list[str] = Field(default_factory=list)


def final_review_model() -> str | None:
    """The model id the final reviewer pins (spec 054): Fable by default.

    Blank ``LSAT_FINAL_REVIEW_MODEL`` disables the pin (the judge's default
    tier model reviews instead); the stage itself is switched by callers.
    """
    from law_ai.core.settings_proxy import settings_proxy as settings

    value = getattr(settings, "LSAT_FINAL_REVIEW_MODEL", "claude-fable-5-1")
    return str(value) if value else None


async def final_review(
    draft: dict[str, Any], *, passage_id: str | None
) -> dict[str, Any]:
    """One independent verdict on an accepted draft from the final-review model."""
    from law_ai.agents_runtime.crews.lsat_draft_judge import LSATDraftJudge

    out = await LSATDraftJudge().run(
        {
            "draft": draft,
            "passage_id": passage_id,
            "proposal_id": None,
            "model_override": final_review_model(),
        }
    )
    body = out.verdict.model_dump()
    body["role"] = "final_review"
    return body


async def draft_variation(
    source_id: str,
    target_archetype_id: str,
    *,
    max_rounds: int = 3,
    use_judge: bool = True,
    use_final_review: bool = True,
) -> VariationResult:
    """Author one variation through the review loop and file it for review.

    The proposal is a ``question`` kind — it promotes through the same
    :func:`~law_ai.lsat.services.proposals.promote_to_bank` as any draft, which
    stamps the target archetype from ``meta.factory.archetype_id`` and keeps
    ``variation_of`` and ``contrast_note`` — with ``meta.revisions`` carrying
    every round's objections so a reviewer sees what was fixed. An unaccepted
    draft is still filed, flagged, rather than discarded after being paid for.
    Degraded (no provider) files nothing: an offline placeholder is not a
    variation.
    """
    from law_ai.agents_runtime.crews.lsat_contrast_author import LSATContrastAuthor
    from law_ai.agents_runtime.crews.lsat_draft_judge import LSATDraftJudge
    from law_ai.lsat.factory.revise import author_with_review

    source = load_bank()[source_id]
    author = LSATContrastAuthor()
    judge = LSATDraftJudge() if use_judge else None

    async def _author(critique: list[str]) -> tuple[dict[str, Any] | None, str, bool]:
        out = await author.run(
            {
                "question_id": source_id,
                "target_archetype_id": target_archetype_id,
                "critique": critique,
            }
        )
        if out.draft is not None:
            return out.draft.model_dump(), out.model, out.degraded
        if out.degraded or not out.issues:
            return None, out.model, True
        # A malformed answer is a round the loop can revise on, not an outage:
        # hand the shape errors to the gates as this round's objections.
        return {"_invalid": list(out.issues)}, out.model, False

    def _gates(draft: dict[str, Any]) -> list[str]:
        invalid = draft.get("_invalid")
        if isinstance(invalid, list):
            return [f"draft was malformed: {i}" for i in invalid]
        return validate_variation(draft, source, target_archetype_id)

    async def _judge(draft: dict[str, Any]) -> dict[str, Any]:
        assert judge is not None
        verdict = await judge.run(
            {"draft": draft, "passage_id": source.passage_id, "proposal_id": None}
        )
        return verdict.verdict.model_dump()

    async def _final(draft: dict[str, Any]) -> dict[str, Any]:
        return await final_review(draft, passage_id=source.passage_id)

    outcome = await author_with_review(
        _author,
        _gates,
        _judge if judge else None,
        max_rounds=max_rounds,
        final_reviewer=_final if use_final_review else None,
    )
    result = VariationResult(
        source_id=source_id,
        target_archetype_id=target_archetype_id,
        accepted=outcome.accepted,
        degraded=outcome.degraded,
        rounds=len(outcome.rounds),
        model=outcome.model,
        issues=list(outcome.rounds[-1].critique) if outcome.rounds else [],
        final_verdict=(
            str(outcome.final_review.get("verdict")) if outcome.final_review else None
        ),
    )
    if outcome.draft is None or "_invalid" in outcome.draft:
        return result
    draft = dict(outcome.draft)
    draft["passage_id"] = source.passage_id
    meta: dict[str, Any] = {
        "variation_of": source_id,
        "factory": {
            "archetype_id": target_archetype_id,
            "executor": "LSATContrastAuthor",
            "mode": "contrast_variation",
        },
        "revisions": {
            "accepted": outcome.accepted,
            "rounds": [r.model_dump() for r in outcome.rounds],
        },
    }
    if outcome.judge is not None:
        meta["factory"]["judge"] = outcome.judge
    if outcome.final_review is not None:
        meta["final_review"] = outcome.final_review
    pid = proposals_store.record_proposal(
        draft,
        agent_trace_id="",
        model=outcome.model,
        confidence=float(draft.get("confidence") or 0.0),
        source_concept_ids=[str(c) for c in draft.get("concepts") or []],
        meta=meta,
        proposal_kind="question",
    )
    result.proposal_id = pid
    return result


__all__ = [
    "MIN_NOTE_CHARS",
    "VariationResult",
    "contrast_set",
    "draft_variation",
    "final_review",
    "final_review_model",
    "pivot_targets",
    "public_contrast_view",
    "root_id_of",
    "stimulus_of",
    "validate_variation",
]
