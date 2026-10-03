"""Question-type playbooks and the diagnosis exercise (spec 053).

A learner who can name the question type before reading the choices has
already done half the work: the type fixes the task, the task fixes the
strategy, and the strategy names the traps. The bank never made that skill
practisable. Items carried concept tags and a free-prose ``orient`` step in
their solve guide, but no machine-readable *type*, and nothing asked the
learner to commit to one.

This module supplies three things:

* **Playbooks** — one per :class:`~law_ai.lsat.factory.taxonomy.Archetype`,
  loaded from ``data/playbooks.json``: the stem cues that give the type away,
  the task in one line, the strategies that apply, the method as steps, and
  the traps the type is built around. Strategies and traps are shared
  catalogs so the same trap can be named across types.
* **A classifier** — :func:`classify` reads the *question sentence* of a
  stem against each playbook's cue patterns. Stem phrasing is how the real
  exam signals type, so it is both the answer key for the exercise and the
  thing the exercise teaches. A stamped ``Question.archetype`` always wins;
  the cue classifier is the fallback for unstamped items and the consistency
  check behind the stamps (``lsat_archetype_backfill``).
* **The exercise** — :func:`diagnosis_options` deals the learner a set of
  candidate types and strategies for one question (never the key), and
  :func:`grade_diagnosis` marks a commitment and returns the playbook as
  feedback, including partial credit for landing in the right *family*.

Nothing here calls a model. Everything is deterministic data over the bank
and the taxonomy, so the static export can carry it verbatim.
"""

from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from law_ai.lsat.factory.taxonomy import Archetype, all_archetypes, get_archetype
from law_ai.lsat.services.bank import Question, Section

DATA_DIR = Path(__file__).resolve().parent / "data"

#: How many candidate types a diagnosis prompt deals. Five mirrors the answer
#: board a learner is used to; a section with fewer archetypes deals fewer.
TYPE_OPTION_COUNT = 5
#: How many candidate strategies a diagnosis prompt deals.
STRATEGY_OPTION_COUNT = 4

ClassifyMethod = Literal["stamped", "cue", "concept", "none"]


class Strategy(BaseModel):
    """A named solving move that applies across question types."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    sections: list[Section]
    summary: str


class Trap(BaseModel):
    """A named wrong-answer pattern the exam plants deliberately."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    name: str
    summary: str


class Playbook(BaseModel):
    """How one question archetype is recognised and solved."""

    archetype_id: str
    #: Coarser grouping used for partial credit: a learner who calls a causal
    #: flaw a general flaw has the family right and the sub-type wrong.
    family: str
    #: Lower runs first when several playbooks' cues match one stem; a
    #: specific type (parallel *flaw*) must beat its general sibling.
    priority: int = 5
    #: Human-readable stem phrasings, shown to the learner as "how to spot it".
    cues: list[str] = Field(min_length=1)
    #: Case-insensitive regexes matched against the stem's question sentence.
    cue_patterns: list[str] = Field(min_length=1)
    #: When set, the cue match only counts if the item carries one of these
    #: concept tags. This is how flaw sub-types share the flaw family's cues
    #: and still resolve to one archetype.
    requires_concepts_any: list[str] = Field(default_factory=list)
    task: str
    strategy_ids: list[str] = Field(min_length=1)
    method: list[str] = Field(min_length=2)
    trap_ids: list[str] = Field(min_length=1)
    #: Archetypes learners most often mistake this one for; they are preferred
    #: as distractors so the exercise drills the distinctions that matter.
    confused_with: list[str] = Field(default_factory=list)


class Classification(BaseModel):
    """Where a question landed and why."""

    question_id: str
    archetype_id: str | None
    method: ClassifyMethod
    #: The cue pattern that decided it, when ``method == "cue"``.
    matched_cue: str | None = None
    #: Every archetype whose cues matched, most specific first. More than one
    #: means the classifier had to break a tie, which a reviewer may want to see.
    candidates: list[str] = Field(default_factory=list)


class DiagnosisOption(BaseModel):
    id: str
    name: str


class DiagnosisPrompt(BaseModel):
    """What the learner is asked before they see the answer choices."""

    question_id: str
    section: Section
    type_options: list[DiagnosisOption]
    strategy_options: list[DiagnosisOption]


class DiagnosisResult(BaseModel):
    """The marked diagnosis plus the playbook as feedback."""

    question_id: str
    section: Section
    archetype_id: str
    archetype_name: str
    family: str
    chosen_archetype: str
    chosen_archetype_name: str | None
    archetype_correct: bool
    #: True when the learner's pick shares the key's family — right kind of
    #: question, wrong sub-type.
    family_correct: bool
    chosen_strategy: str | None
    strategy_correct: bool | None
    #: The cue in this stem that gives the type away, when one can be quoted.
    matched_cue: str | None
    playbook: dict[str, Any]


# ---------------------------------------------------------------------------
# Loaders (lazy + cached)
# ---------------------------------------------------------------------------


def _raw() -> dict[str, Any]:
    path = DATA_DIR / "playbooks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("playbooks.json must be an object")
    return data


@lru_cache(maxsize=1)
def load_strategies() -> dict[str, Strategy]:
    """The strategy catalog, keyed by id.

    >>> "negation-test" in load_strategies()
    True
    """
    items = [Strategy.model_validate(x) for x in _raw().get("strategies", [])]
    return {s.id: s for s in items}


@lru_cache(maxsize=1)
def load_traps() -> dict[str, Trap]:
    """The trap catalog, keyed by id.

    >>> load_traps()["opposite-answer"].name
    'The opposite answer'
    """
    items = [Trap.model_validate(x) for x in _raw().get("traps", [])]
    return {t.id: t for t in items}


@lru_cache(maxsize=1)
def load_playbooks() -> dict[str, Playbook]:
    """One playbook per question archetype, keyed by archetype id.

    Fails loudly on an unknown archetype, a dangling strategy or trap id, or an
    archetype with no playbook: the exercise's answer key must be complete.

    >>> sorted(load_playbooks())[:2]
    ['lg-acceptability', 'lg-could-be-true-except']
    """
    strategies = load_strategies()
    traps = load_traps()
    known = {a.id: a for a in all_archetypes()}
    books: dict[str, Playbook] = {}
    for entry in _raw().get("playbooks", []):
        pb = Playbook.model_validate(entry)
        if pb.archetype_id not in known:
            raise ValueError(f"playbook for unknown archetype {pb.archetype_id!r}")
        if pb.archetype_id in books:
            raise ValueError(f"duplicate playbook for {pb.archetype_id!r}")
        for sid in pb.strategy_ids:
            if sid not in strategies:
                raise ValueError(f"{pb.archetype_id}: unknown strategy {sid!r}")
        for tid in pb.trap_ids:
            if tid not in traps:
                raise ValueError(f"{pb.archetype_id}: unknown trap {tid!r}")
        for other in pb.confused_with:
            if other not in known:
                raise ValueError(f"{pb.archetype_id}: confused_with unknown {other!r}")
        for pattern in pb.cue_patterns:
            re.compile(pattern, re.IGNORECASE)
        books[pb.archetype_id] = pb
    missing = sorted(set(known) - set(books))
    if missing:
        raise ValueError(f"archetypes without a playbook: {missing}")
    return books


def reset_playbook_caches() -> None:
    """Drop every loader cache. Tests use this when they edit the data dir."""
    load_strategies.cache_clear()
    load_traps.cache_clear()
    load_playbooks.cache_clear()


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def question_sentence(stem: str) -> str:
    """The part of a stem that asks the question.

    LR stems carry the argument and then, after a blank line, the question;
    RC and LG stems are the question alone. Matching cues against the last
    paragraph keeps a stimulus that happens to say "must be true" from
    classifying itself.

    >>> question_sentence("Premise.\\n\\nWhich one of the following must be true?")
    'Which one of the following must be true?'
    """
    parts = [p.strip() for p in re.split(r"\n\s*\n", stem.strip()) if p.strip()]
    return parts[-1] if parts else stem.strip()


def _cue_hit(pb: Playbook, text: str) -> str | None:
    for pattern in pb.cue_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


def _concept_overlap(q: Question, archetype: Archetype) -> int:
    return len(set(q.concepts) & set(archetype.concepts))


def classify(q: Question) -> Classification:
    """Which archetype a question instantiates.

    A stamped ``archetype`` is authoritative. Otherwise the question sentence
    is matched against every same-section playbook's cues; among the hits,
    the lowest ``priority`` wins, then the largest concept overlap with the
    archetype, then id. With no cue hit at all the item falls back to the
    unique archetype whose *primary* concept it carries (the coverage
    census's own contract), and to ``None`` when even that is ambiguous.

    >>> from law_ai.lsat.services.bank import load_bank
    >>> classify(load_bank()["lr-002"]).archetype_id
    'lr-weaken'
    """
    if q.archetype is not None:
        return Classification(
            question_id=q.id, archetype_id=q.archetype, method="stamped"
        )
    books = load_playbooks()
    text = question_sentence(q.stem)
    hits: list[tuple[int, int, str, str]] = []
    for pb in books.values():
        archetype = get_archetype(pb.archetype_id)
        if archetype.section != q.section:
            continue
        if pb.requires_concepts_any and not (
            set(pb.requires_concepts_any) & set(q.concepts)
        ):
            continue
        pattern = _cue_hit(pb, text)
        if pattern is None:
            continue
        hits.append(
            (pb.priority, -_concept_overlap(q, archetype), pb.archetype_id, pattern)
        )
    if hits:
        hits.sort()
        _, _, winner, pattern = hits[0]
        return Classification(
            question_id=q.id,
            archetype_id=winner,
            method="cue",
            matched_cue=pattern,
            candidates=[h[2] for h in hits],
        )
    # No cue: the primary-concept contract, as coverage.py applies it.
    primaries = [
        a.id
        for a in all_archetypes()
        if a.section == q.section and a.concepts[0] in q.concepts
    ]
    if len(primaries) == 1:
        return Classification(
            question_id=q.id,
            archetype_id=primaries[0],
            method="concept",
            candidates=primaries,
        )
    return Classification(
        question_id=q.id, archetype_id=None, method="none", candidates=primaries
    )


def archetype_of(q: Question) -> Archetype | None:
    """The archetype a question drills, or None when it cannot be decided."""
    result = classify(q)
    if result.archetype_id is None:
        return None
    return get_archetype(result.archetype_id)


def playbook_for(q: Question) -> Playbook | None:
    """The playbook that solves this question, or None when unclassifiable."""
    archetype = archetype_of(q)
    if archetype is None:
        return None
    return load_playbooks()[archetype.id]


# ---------------------------------------------------------------------------
# The exercise
# ---------------------------------------------------------------------------


def _option(archetype: Archetype) -> DiagnosisOption:
    return DiagnosisOption(id=archetype.id, name=archetype.name)


def diagnosis_options(q: Question, *, seed: str | None = None) -> DiagnosisPrompt:
    """Deal the candidate types and strategies for one question.

    The key is always among the options and its position is shuffled by
    ``seed`` (the question id by default, so a test can pin the deal). Type
    distractors are drawn first from the key's ``confused_with`` list and then
    from the rest of the section, so the exercise drills the distinctions the
    exam actually trades on. Strategy distractors come from the same section's
    catalog. Nothing in the prompt reveals which option is the key.

    >>> from law_ai.lsat.services.bank import load_bank
    >>> prompt = diagnosis_options(load_bank()["lr-002"])
    >>> any(o.id == "lr-weaken" for o in prompt.type_options)
    True
    """
    playbook = playbook_for(q)
    if playbook is None:
        raise ValueError(f"{q.id} has no classifiable question type")
    key = get_archetype(playbook.archetype_id)
    rng = random.Random(seed if seed is not None else q.id)

    section_pool = [
        a for a in all_archetypes() if a.section == q.section and a.id != key.id
    ]
    preferred = [a for a in section_pool if a.id in playbook.confused_with]
    rest = [a for a in section_pool if a.id not in playbook.confused_with]
    rng.shuffle(preferred)
    rng.shuffle(rest)
    distractors = (preferred + rest)[: TYPE_OPTION_COUNT - 1]
    types = [_option(key)] + [_option(a) for a in distractors]
    rng.shuffle(types)

    strategies = load_strategies()
    key_strategies = [strategies[s] for s in playbook.strategy_ids]
    others = [
        s
        for s in strategies.values()
        if q.section in s.sections and s.id not in playbook.strategy_ids
    ]
    rng.shuffle(others)
    # The primary strategy is always dealt; the rest of the key's strategies
    # are *also* right answers and may appear, which grade_diagnosis honours.
    dealt = [key_strategies[0], *others[: STRATEGY_OPTION_COUNT - 1]]
    rng.shuffle(dealt)
    return DiagnosisPrompt(
        question_id=q.id,
        section=q.section,
        type_options=types,
        strategy_options=[DiagnosisOption(id=s.id, name=s.name) for s in dealt],
    )


def public_playbook_view(pb: Playbook) -> dict[str, Any]:
    """A playbook with its strategy and trap ids resolved for display."""
    archetype = get_archetype(pb.archetype_id)
    strategies = load_strategies()
    traps = load_traps()
    return {
        "archetype_id": pb.archetype_id,
        "name": archetype.name,
        "section": archetype.section,
        "family": pb.family,
        "concepts": list(archetype.concepts),
        "cues": list(pb.cues),
        "task": pb.task,
        "strategies": [strategies[s].model_dump() for s in pb.strategy_ids],
        "method": list(pb.method),
        "traps": [traps[t].model_dump() for t in pb.trap_ids],
        "confused_with": [
            {"id": other, "name": get_archetype(other).name}
            for other in pb.confused_with
        ],
    }


def grade_diagnosis(
    q: Question,
    *,
    chosen_archetype: str,
    chosen_strategy: str | None = None,
) -> DiagnosisResult:
    """Mark a learner's type and strategy call and return the playbook.

    ``strategy_correct`` is None when no strategy was submitted. Any of the
    key's strategies counts as correct, not only the one that was dealt.

    >>> from law_ai.lsat.services.bank import load_bank
    >>> r = grade_diagnosis(load_bank()["lr-002"], chosen_archetype="lr-causal-flaw")
    >>> (r.archetype_correct, r.family_correct)
    (False, False)
    """
    playbook = playbook_for(q)
    if playbook is None:
        raise ValueError(f"{q.id} has no classifiable question type")
    books = load_playbooks()
    key = get_archetype(playbook.archetype_id)
    chosen_book = books.get(chosen_archetype)
    chosen_name = get_archetype(chosen_archetype).name if chosen_book else None
    classification = classify(q)
    matched_cue = _quote_cue(playbook, question_sentence(q.stem))
    return DiagnosisResult(
        question_id=q.id,
        section=q.section,
        archetype_id=key.id,
        archetype_name=key.name,
        family=playbook.family,
        chosen_archetype=chosen_archetype,
        chosen_archetype_name=chosen_name,
        archetype_correct=chosen_archetype == key.id,
        family_correct=bool(chosen_book and chosen_book.family == playbook.family),
        chosen_strategy=chosen_strategy,
        strategy_correct=(
            None
            if chosen_strategy is None
            else chosen_strategy in playbook.strategy_ids
        ),
        matched_cue=matched_cue or classification.matched_cue,
        playbook=public_playbook_view(playbook),
    )


def _quote_cue(pb: Playbook, text: str) -> str | None:
    """The words in this stem that the playbook's cue pattern caught."""
    for pattern in pb.cue_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and m.group(0).strip():
            return m.group(0).strip()
    return None


def playbooks_for_section(section: Section | None = None) -> list[dict[str, Any]]:
    """Every playbook (optionally one section's), as public views, by id."""
    out = []
    for pb in sorted(load_playbooks().values(), key=lambda p: p.archetype_id):
        if section is not None and get_archetype(pb.archetype_id).section != section:
            continue
        out.append(public_playbook_view(pb))
    return out


__all__ = [
    "STRATEGY_OPTION_COUNT",
    "TYPE_OPTION_COUNT",
    "Classification",
    "DiagnosisOption",
    "DiagnosisPrompt",
    "DiagnosisResult",
    "Playbook",
    "Strategy",
    "Trap",
    "archetype_of",
    "classify",
    "diagnosis_options",
    "grade_diagnosis",
    "load_playbooks",
    "load_strategies",
    "load_traps",
    "playbook_for",
    "playbooks_for_section",
    "public_playbook_view",
    "question_sentence",
    "reset_playbook_caches",
]
