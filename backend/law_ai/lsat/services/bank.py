"""LSAT question bank loader (spec 005, refactored 2026-05-03).

Supports all current LSAT sections — Logical Reasoning (LR), Reading
Comprehension (RC), Logic Games / Analytical Reasoning (LG), and Argumentative
Writing (WS) — plus a catalog of reusable concept explanations and
passage/game contexts.

``WS`` is a section for *metadata and concept-tagging purposes only*: an
argumentative-writing task produces an essay, not a keyed choice, so it has no
:class:`Question` representation and lives in
:mod:`law_ai.lsat.services.writing` instead. :class:`Question` rejects the code
outright (spec 047 FR-1) so writing content can never masquerade as an item
with an answer key.

The loader is lazy + cached and tolerates missing per-section files so a
fresh checkout still works after partial data updates.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DATA_DIR = Path(__file__).resolve().parent / "data"

Section = Literal["LR", "RC", "LG", "WS"]

# The multiple-choice subset of ``Section``. Every :class:`Question` carries
# one of these; ``WS`` is deliberately excluded (see the module docstring).
MCQ_SECTIONS: tuple[Section, ...] = ("LR", "RC", "LG")
ChoiceLabel = Literal["A", "B", "C", "D", "E"]
# Spec 047 FR-8. The original three bands are kept verbatim so every stored
# item stays valid; ``intro`` and ``elite`` extend the scale at either end.
#
#   intro — the pattern in its cleanest form, one inference, no trap. Where a
#           learner meets an archetype for the first time.
#   easy  — a real but gentle instance; the trap exists but is visible.
#   med   — the modal difficulty of a scored section.
#   hard  — two or more chained inferences, or a trap that survives a careful
#           first read.
#   elite — the handful of items per exam that separate the top band: the
#           credited answer is defensible only after the four distractors have
#           each been positively ruled out.
Difficulty = Literal["intro", "easy", "med", "hard", "elite"]

#: Easiest to hardest. The single source of ordering — sort and bucket by this
#: rather than by the literal's declaration order or alphabetically.
DIFFICULTY_ORDER: tuple[Difficulty, ...] = ("intro", "easy", "med", "hard", "elite")

# Back-compat alias kept for tests / external consumers that imported the
# original ``QuestionType`` literal when only LR existed.
QuestionType = Section


class Choice(BaseModel):
    label: ChoiceLabel
    text: str


class Reference(BaseModel):
    title: str
    url: str | None = None
    note: str | None = None


class PassageContext(BaseModel):
    """Shared context attached to a group of questions.

    Used for Reading Comprehension passages and Logic Games setups. A
    *comparative* RC set (spec 047 FR-9) carries a second passage in
    ``passage_b``: the real exam pairs two short passages on one topic and
    asks about their relationship, which no single-text field can represent.
    """

    id: str
    section: Section
    title: str
    summary: str | None = None
    passage: str | None = Field(
        default=None,
        description="Full passage text (RC). On a comparative set this is "
        "Passage A. None for LG sets.",
    )
    passage_b: str | None = Field(
        default=None,
        description="Passage B of a comparative RC set; None for a single-text "
        "passage or an LG setup.",
    )
    title_a: str | None = Field(
        default=None,
        description="Heading for Passage A (comparative sets only).",
    )
    title_b: str | None = Field(
        default=None,
        description="Heading for Passage B (comparative sets only).",
    )
    setup: str | None = Field(
        default=None,
        description="Game narrative (LG). None for RC sets.",
    )
    rules: list[str] = Field(
        default_factory=list,
        description="Constraint list (LG). Empty for RC sets.",
    )
    source: str = "original (CC0)"

    @property
    def is_comparative(self) -> bool:
        """True when this set pairs two passages (spec 047 FR-9)."""
        return bool(self.passage_b)

    @model_validator(mode="after")
    def _comparative_sets_are_well_formed(self) -> PassageContext:
        if self.passage_b is None:
            return self
        if self.section != "RC":
            raise ValueError(
                f"{self.id}: passage_b is a Reading Comprehension construct; "
                f"section is {self.section!r}"
            )
        if not self.passage:
            raise ValueError(
                f"{self.id}: comparative set has Passage B but no Passage A"
            )
        if not (self.title_a and self.title_b):
            # Without headings a reader cannot tell which text a question is
            # about — and every comparative question stem names one of them.
            raise ValueError(
                f"{self.id}: comparative set must name both passages "
                "(title_a and title_b)"
            )
        return self


#: How a bank item was reviewed before it was allowed to serve learners.
#: ``editorial`` is a person reading the item and approving it (the HITL queue
#: stamps this); ``machine-judge`` is an automated adversarial pass, which is
#: weaker and must never be labelled as editorial; ``proof`` is a
#: finite-model-checked synthesized item (spec 049).
#:
#: There is deliberately no value for "a person wrote this and it was reviewed
#: in the pull request that added it" (BL-20260905-51). That path leaves its
#: record in git, not in the data file, and inventing a ``pr-review`` method
#: would mean writing a reviewer name no one can check. The convention is
#: instead: ``review is None`` on a hand-authored item means PR review, and a
#: *machine*-authored item must always carry a record (test_bank_review.py
#: enforces exactly that asymmetry).
ReviewMethod = Literal["editorial", "machine-judge", "proof"]


class QuestionReview(BaseModel):
    """The review a bank item actually received (BL-20260429-19).

    Bulk-imported factory items used to carry only a ``source`` string, so
    "reviewed" and "machine-checked" were indistinguishable after the fact.
    This records which happened, by whom, and when — an item can be trusted
    exactly as far as its review record says.
    """

    method: ReviewMethod
    reviewed_by: str = Field(description="Person or system that did the review.")
    reviewed_at: str = Field(description="ISO date of the review.")
    note: str | None = None


class Question(BaseModel):
    id: str
    section: Section
    type: Section = Field(
        ..., description="Alias for ``section`` kept for backward compatibility."
    )
    difficulty: Difficulty
    stem: str
    choices: list[Choice] = Field(min_length=5, max_length=5)
    correct: ChoiceLabel
    explanation: str
    source: str
    concepts: list[str] = Field(
        default_factory=list,
        description="Concept catalog ids tagging the reasoning patterns at play.",
    )
    references: list[Reference] = Field(default_factory=list)
    passage_id: str | None = Field(
        default=None,
        description="Set on RC + LG items to link them to a PassageContext.",
    )
    #: Spec 054: the bank id of the question this one is a *contrast variation*
    #: of — same stimulus, re-asked as a different archetype. None on a root.
    variation_of: str | None = None
    #: Spec 054: what changes between this variation and its root — how the
    #: task moves the key and which traps swap sides. Spoiler-class content:
    #: served only after grading, like the explanation.
    contrast_note: str | None = None
    archetype: str | None = Field(
        default=None,
        description="Factory taxonomy archetype this item instantiates "
        "(BL-20260905-54). Stamped at promotion from the generation job that "
        "drafted it. None means it predates the stamp, and the coverage "
        "census falls back to matching on the archetype's primary concept.",
    )
    review: QuestionReview | None = Field(
        default=None,
        description="How this item was reviewed before it entered the bank "
        "(BL-20260429-19). None is the hand-authored convention "
        "(BL-20260905-51): the item was written by a person and reviewed in "
        "the pull request that added it, which leaves no record here. A "
        "machine-authored item may never rely on it — see ReviewMethod.",
    )

    @model_validator(mode="before")
    @classmethod
    def _backfill_section_type(cls, data: object) -> object:
        """Allow legacy items that only carry ``type`` (or only ``section``)."""
        if isinstance(data, dict):
            section = data.get("section") or data.get("type")
            if section is not None:
                data.setdefault("section", section)
                data.setdefault("type", section)
        return data

    @model_validator(mode="after")
    def _reject_writing_section(self) -> Question:
        """Spec 047 FR-1/AC-2: ``WS`` has no keyed-choice representation.

        Writing tasks produce an essay scored against a rubric, so they carry
        no ``correct`` label and no distractors. Rejecting the code here keeps
        the invariant at the one place it matters instead of making every
        downstream consumer defend against a five-choice writing item.
        """
        if self.section == "WS" or self.type == "WS":
            raise ValueError(
                "section 'WS' (Argumentative Writing) has no multiple-choice "
                "form — author it as a WritingPrompt in "
                "law_ai.lsat.services.writing instead"
            )
        return self


class Concept(BaseModel):
    """An entry in the LSAT concept catalog."""

    id: str
    name: str
    sections: list[Section]
    summary: str
    detail: str | None = None
    examples: list[str] = Field(default_factory=list)
    see_also: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


class SectionInfo(BaseModel):
    """Top-level metadata for an LSAT section."""

    code: Section
    name: str
    description: str
    format: str
    timing: str
    scoring: str
    skills: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


class PublicQuestion(BaseModel):
    """Question payload returned to clients (no answer key)."""

    id: str
    section: Section
    type: Section
    difficulty: Difficulty
    stem: str
    choices: list[Choice]
    concepts: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    passage_id: str | None = None
    #: The root question this is a contrast variation of (spec 054). Safe to
    #: ship: it names a sibling, not the key.
    variation_of: str | None = None
    #: The signed permutation this serve used (BL-20260606-01). Present only
    #: when the question was requested with ``shuffle``; the client echoes it
    #: back at grade time so the answer is read in the order it was shown.
    remap: str | None = None


# ---------------------------------------------------------------------------
# Loaders (lazy + cached)
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_bank() -> dict[str, Question]:
    """Load every section's question bank, keyed by question id.

    Reads ``lr_bank.json``, ``rc_bank.json`` and ``lg_bank.json`` from the
    ``data/`` directory; missing files are skipped so partial data sets
    remain valid. Cached for the process lifetime.
    """
    items: list[Question] = []
    for fname in ("lr_bank.json", "rc_bank.json", "lg_bank.json"):
        path = DATA_DIR / fname
        if not path.is_file():
            continue
        raw = _load_json(path)
        for entry in raw.get("items", []):
            items.append(Question.model_validate(entry))

    if not items:
        raise RuntimeError(f"No LSAT bank files found under {DATA_DIR}")

    # Defensive: every item carries 5 choices A–E (the public contract).
    for q in items:
        labels = [c.label for c in q.choices]
        if labels != ["A", "B", "C", "D", "E"]:
            raise ValueError(f"{q.id} must have choices A-E in order")

    return {q.id: q for q in items}


@lru_cache(maxsize=1)
def load_passages() -> dict[str, PassageContext]:
    """Load passage / game contexts shared across multiple questions."""
    path = DATA_DIR / "passages.json"
    if not path.is_file():
        return {}
    raw = _load_json(path)
    items = [PassageContext.model_validate(x) for x in raw.get("items", [])]
    return {p.id: p for p in items}


@lru_cache(maxsize=1)
def load_concepts() -> dict[str, Concept]:
    """Load the concept catalog used for tagging + tutoring."""
    path = DATA_DIR / "concepts.json"
    if not path.is_file():
        return {}
    raw = _load_json(path)
    items = [Concept.model_validate(x) for x in raw.get("items", [])]
    return {c.id: c for c in items}


@lru_cache(maxsize=1)
def load_sections() -> dict[str, SectionInfo]:
    """Load top-level section metadata (description, scoring, tips, …)."""
    path = DATA_DIR / "sections.json"
    if not path.is_file():
        return {}
    raw = _load_json(path)
    items = [SectionInfo.model_validate(x) for x in raw.get("items", [])]
    return {s.code: s for s in items}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def public_view(q: Question) -> PublicQuestion:
    """Strip the answer key + rationale so the question is safe to ship."""
    return PublicQuestion(
        id=q.id,
        section=q.section,
        type=q.type,
        difficulty=q.difficulty,
        stem=q.stem,
        choices=q.choices,
        concepts=q.concepts,
        references=q.references,
        passage_id=q.passage_id,
        variation_of=q.variation_of,
    )


def reset_caches() -> None:
    """Drop every loader cache. Tests use this when they edit the data dir."""
    load_bank.cache_clear()
    load_passages.cache_clear()
    load_concepts.cache_clear()
    load_sections.cache_clear()
