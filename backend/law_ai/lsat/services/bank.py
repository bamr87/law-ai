"""LSAT question bank loader (spec 005, refactored 2026-05-03).

Supports all current LSAT sections — Logical Reasoning (LR), Reading
Comprehension (RC), and Logic Games / Analytical Reasoning (LG) — plus a
catalog of reusable concept explanations and passage/game contexts.

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

Section = Literal["LR", "RC", "LG"]
ChoiceLabel = Literal["A", "B", "C", "D", "E"]
Difficulty = Literal["easy", "med", "hard"]

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

    Used for Reading Comprehension passages and Logic Games setups.
    """

    id: str
    section: Section
    title: str
    summary: str | None = None
    passage: str | None = Field(
        default=None,
        description="Full passage text (RC). None for LG sets.",
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
        for entry in raw.get("items", []):  # type: ignore[union-attr]
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
    items = [PassageContext.model_validate(x) for x in raw.get("items", [])]  # type: ignore[union-attr]
    return {p.id: p for p in items}


@lru_cache(maxsize=1)
def load_concepts() -> dict[str, Concept]:
    """Load the concept catalog used for tagging + tutoring."""
    path = DATA_DIR / "concepts.json"
    if not path.is_file():
        return {}
    raw = _load_json(path)
    items = [Concept.model_validate(x) for x in raw.get("items", [])]  # type: ignore[union-attr]
    return {c.id: c for c in items}


@lru_cache(maxsize=1)
def load_sections() -> dict[str, SectionInfo]:
    """Load top-level section metadata (description, scoring, tips, …)."""
    path = DATA_DIR / "sections.json"
    if not path.is_file():
        return {}
    raw = _load_json(path)
    items = [SectionInfo.model_validate(x) for x in raw.get("items", [])]  # type: ignore[union-attr]
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
    )


def reset_caches() -> None:
    """Drop every loader cache. Tests use this when they edit the data dir."""
    load_bank.cache_clear()
    load_passages.cache_clear()
    load_concepts.cache_clear()
    load_sections.cache_clear()
