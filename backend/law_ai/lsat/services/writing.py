"""LSAT Argumentative Writing store (spec 047 FR-1/FR-2).

The writing section is the one LSAT task that produces prose rather than a
keyed choice, so it gets its own content type instead of being bent into
:class:`~law_ai.lsat.services.bank.Question`. A *writing prompt* presents a
debatable issue, the principal positions in play, and several stated
perspectives; the test taker argues for one position and answers the other.
A *rubric* is the weighted criteria x performance bands the response is read
against — shipped alongside the prompt so a learner can self-score with no
model call at all (NFR-OFFLINE-1).

Follows the :mod:`law_ai.lsat.services.bank` / :mod:`~.guides` pattern:
file-backed JSON, Pydantic validation, lazy ``@lru_cache`` loaders that fail
loudly on cross-reference drift, and a public view helper that withholds the
model response the same way ``public_guide_view`` withholds spoiler steps —
reading the model answer before drafting destroys the exercise.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field, model_validator

from law_ai.lsat.services import bank as _bank
from law_ai.lsat.services.bank import Difficulty, Reference

_RUBRICS_FILE = "writing_rubrics.json"
_PROMPTS_FILE = "writing_prompts.json"

#: Weights across a rubric's criteria must sum to 1.0 within this tolerance.
_WEIGHT_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------


class RubricBand(BaseModel):
    """One performance level on the scale (higher ``level`` is stronger)."""

    level: int = Field(ge=1)
    label: str
    descriptor: str


class RubricCriterion(BaseModel):
    """One weighted dimension a response is read against."""

    id: str
    name: str
    description: str
    weight: float = Field(gt=0.0, le=1.0)
    look_for: list[str] = Field(
        default_factory=list,
        description="Observable moves a reader can point at, so the criterion "
        "is checkable rather than a matter of taste.",
    )
    band_notes: dict[str, str] = Field(
        default_factory=dict,
        description="Band level (as a string key) -> what this criterion looks "
        "like at that level.",
    )


class WritingRubric(BaseModel):
    """Weighted criteria x ordered performance bands."""

    id: str
    name: str
    version: int = 1
    summary: str
    bands: list[RubricBand] = Field(min_length=2)
    criteria: list[RubricCriterion] = Field(min_length=1)
    source: str = "original (CC0)"

    @model_validator(mode="after")
    def _internally_consistent(self) -> WritingRubric:
        levels = [b.level for b in self.bands]
        if len(set(levels)) != len(levels):
            raise ValueError(f"rubric {self.id!r} has duplicate band levels")
        if levels != sorted(levels):
            raise ValueError(f"rubric {self.id!r} bands must ascend by level")

        ids = [c.id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError(f"rubric {self.id!r} has duplicate criterion ids")

        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > _WEIGHT_TOLERANCE:
            raise ValueError(
                f"rubric {self.id!r} criterion weights sum to {total}, not 1.0"
            )

        known = {str(b.level) for b in self.bands}
        for crit in self.criteria:
            unknown = sorted(set(crit.band_notes) - known)
            if unknown:
                raise ValueError(
                    f"rubric {self.id!r} criterion {crit.id!r} annotates "
                    f"unknown band level(s): {unknown}"
                )
        return self

    @property
    def criterion_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.criteria)

    @property
    def band_levels(self) -> tuple[int, ...]:
        return tuple(b.level for b in self.bands)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


class WritingPosition(BaseModel):
    """One of the principal stances a writer may argue for."""

    id: str
    name: str
    summary: str


class WritingPerspective(BaseModel):
    """A stated consideration the writer is expected to engage with."""

    id: str
    text: str


class ModelAnnotation(BaseModel):
    """Where the model response earns one rubric criterion."""

    criterion_id: str
    note: str


class ModelResponse(BaseModel):
    """A worked example essay, annotated criterion by criterion."""

    position_id: str
    thesis: str
    essay: str
    annotations: list[ModelAnnotation] = Field(default_factory=list)


class SelfCheckItem(BaseModel):
    """One yes/no question a learner asks of their own draft."""

    criterion_id: str
    prompt: str


class WritingPrompt(BaseModel):
    """One argumentative-writing task."""

    id: str
    title: str
    rubric_id: str
    difficulty: Difficulty
    issue: str = Field(description="The debatable question in one sentence.")
    context: str = Field(description="Background framing the debate.")
    positions: list[WritingPosition] = Field(min_length=2)
    perspectives: list[WritingPerspective] = Field(min_length=3)
    task: str = Field(description="The instruction shown to the test taker.")
    prewriting_minutes: int = Field(default=15, ge=0, le=60)
    time_limit_minutes: int = Field(default=35, ge=5, le=120)
    concepts: list[str] = Field(default_factory=list)
    model_response: ModelResponse
    self_check: list[SelfCheckItem] = Field(min_length=1)
    references: list[Reference] = Field(default_factory=list)
    source: str = "original (CC0)"

    @model_validator(mode="after")
    def _internally_consistent(self) -> WritingPrompt:
        pos_ids = [p.id for p in self.positions]
        if len(set(pos_ids)) != len(pos_ids):
            raise ValueError(f"prompt {self.id!r} has duplicate position ids")
        if self.model_response.position_id not in pos_ids:
            raise ValueError(
                f"prompt {self.id!r} model response argues for unknown position "
                f"{self.model_response.position_id!r}"
            )
        persp_ids = [p.id for p in self.perspectives]
        if len(set(persp_ids)) != len(persp_ids):
            raise ValueError(f"prompt {self.id!r} has duplicate perspective ids")
        return self


class PublicWritingPrompt(BaseModel):
    """Prompt payload safe to serve before the learner has drafted anything.

    Carries no model response — the writing equivalent of stripping the answer
    key in :func:`~law_ai.lsat.services.bank.public_view`.
    """

    id: str
    title: str
    rubric_id: str
    difficulty: Difficulty
    issue: str
    context: str
    positions: list[WritingPosition]
    perspectives: list[WritingPerspective]
    task: str
    prewriting_minutes: int
    time_limit_minutes: int
    concepts: list[str] = Field(default_factory=list)
    self_check: list[SelfCheckItem] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    has_model_response: bool = True


# ---------------------------------------------------------------------------
# Loaders (lazy + cached, mirrors bank.py / guides.py)
# ---------------------------------------------------------------------------


def _read(fname: str) -> dict[str, Any] | None:
    # Resolve through the bank module so test sandboxes that monkeypatch
    # ``bank.DATA_DIR`` redirect these loaders too (the guides.py convention).
    path = _bank.DATA_DIR / fname
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=1)
def load_writing_rubrics() -> dict[str, WritingRubric]:
    """Load every writing rubric, keyed by id."""
    raw = _read(_RUBRICS_FILE)
    if raw is None:
        return {}
    out: dict[str, WritingRubric] = {}
    for entry in raw.get("items", []):
        rubric = WritingRubric.model_validate(entry)
        if rubric.id in out:
            raise ValueError(f"duplicate writing rubric id {rubric.id!r}")
        out[rubric.id] = rubric
    return out


@lru_cache(maxsize=1)
def load_writing_prompts() -> dict[str, WritingPrompt]:
    """Load every writing prompt, keyed by id.

    Fails loudly on cross-reference drift — an unknown rubric, a self-check or
    annotation naming a criterion the rubric does not define, or a concept tag
    outside the catalog. Content drift must surface in tests and CI, never at
    user request time (spec 047 AC-1).
    """
    raw = _read(_PROMPTS_FILE)
    if raw is None:
        return {}

    rubrics = load_writing_rubrics()
    catalog = set(_bank.load_concepts())
    out: dict[str, WritingPrompt] = {}

    for entry in raw.get("items", []):
        prompt = WritingPrompt.model_validate(entry)
        if prompt.id in out:
            raise ValueError(f"duplicate writing prompt id {prompt.id!r}")

        rubric = rubrics.get(prompt.rubric_id)
        if rubric is None:
            raise ValueError(
                f"writing prompt {prompt.id!r} references unknown rubric "
                f"{prompt.rubric_id!r}"
            )
        known = set(rubric.criterion_ids)

        unknown_checks = sorted({s.criterion_id for s in prompt.self_check} - known)
        if unknown_checks:
            raise ValueError(
                f"writing prompt {prompt.id!r} self-check references criteria "
                f"not in rubric {rubric.id!r}: {unknown_checks}"
            )
        unknown_notes = sorted(
            {a.criterion_id for a in prompt.model_response.annotations} - known
        )
        if unknown_notes:
            raise ValueError(
                f"writing prompt {prompt.id!r} model response annotates criteria "
                f"not in rubric {rubric.id!r}: {unknown_notes}"
            )
        if catalog:
            unknown_concepts = sorted(set(prompt.concepts) - catalog)
            if unknown_concepts:
                raise ValueError(
                    f"writing prompt {prompt.id!r} tags unknown concept(s): "
                    f"{unknown_concepts}"
                )
        out[prompt.id] = prompt
    return out


def reset_writing_caches() -> None:
    """Drop both loader caches. Tests use this when they edit the data dir."""
    load_writing_rubrics.cache_clear()
    load_writing_prompts.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def default_rubric() -> WritingRubric | None:
    """The rubric to use when a caller names none (lowest id wins, stably)."""
    rubrics = load_writing_rubrics()
    if not rubrics:
        return None
    return rubrics[sorted(rubrics)[0]]


def rubric_for(prompt: WritingPrompt) -> WritingRubric:
    """The rubric a prompt is read against (load-time validated to exist)."""
    return load_writing_rubrics()[prompt.rubric_id]


def public_prompt_view(prompt: WritingPrompt) -> PublicWritingPrompt:
    """Strip the model response so the prompt is safe to serve pre-draft."""
    return PublicWritingPrompt(
        id=prompt.id,
        title=prompt.title,
        rubric_id=prompt.rubric_id,
        difficulty=prompt.difficulty,
        issue=prompt.issue,
        context=prompt.context,
        positions=prompt.positions,
        perspectives=prompt.perspectives,
        task=prompt.task,
        prewriting_minutes=prompt.prewriting_minutes,
        time_limit_minutes=prompt.time_limit_minutes,
        concepts=list(prompt.concepts),
        self_check=prompt.self_check,
        references=prompt.references,
        has_model_response=True,
    )
