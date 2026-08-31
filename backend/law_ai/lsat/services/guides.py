"""LSAT solve-guide store (spec 041 FR-1..FR-4).

A *solve guide* is an ordered, machine-renderable walkthrough of one bank
question: each step carries prose plus an optional typed representation
(sequence board, grouping grid, symbolized rules, argument map, passage map)
that the frontend renders incrementally as a progressive hint system.

Follows the :mod:`law_ai.lsat.services.bank` pattern: file-backed JSON,
Pydantic validation, lazy ``@lru_cache`` loaders, and a public view helper
that withholds spoiler content the same way ``public_view`` withholds the
answer key.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from law_ai.lsat.services import bank as _bank

StepKind = Literal[
    "orient", "inventory", "symbolize", "diagram", "infer", "eliminate", "answer"
]

# ---------------------------------------------------------------------------
# Typed representations (spec 041 FR-2)
# ---------------------------------------------------------------------------


class SequenceRep(BaseModel):
    """Ordering-game board: horizontal slots + the entity inventory."""

    rep_type: Literal["sequence"] = "sequence"
    slots: list[str] = Field(min_length=1)
    entities: list[str] = Field(min_length=1)
    placements: dict[str, str] = Field(
        default_factory=dict, description="slot label -> entity fixed there."
    )
    exclusions: dict[str, list[str]] = Field(
        default_factory=dict, description="slot label -> entities barred from it."
    )
    note: str | None = None


class GridCell(BaseModel):
    row: str
    column: str
    mark: Literal["yes", "no", "maybe"]
    note: str | None = None


class GridRep(BaseModel):
    """Grouping / assignment board rendered as rows x columns."""

    rep_type: Literal["grid"] = "grid"
    rows: list[str] = Field(min_length=1)
    columns: list[str] = Field(min_length=1)
    cells: list[GridCell] = Field(default_factory=list)
    note: str | None = None


class NotationRule(BaseModel):
    rule_text: str
    symbols: str
    note: str | None = None


class NotationRep(BaseModel):
    """Rules translated into standard symbolic notation, one per line."""

    rep_type: Literal["notation"] = "notation"
    rules: list[NotationRule] = Field(min_length=1)


class ArgumentNode(BaseModel):
    id: str
    role: Literal["premise", "conclusion", "assumption", "objection"]
    text: str


class ArgumentEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    relation: Literal["supports", "opposes"]


class ArgumentMapRep(BaseModel):
    """Premises-supporting-conclusion structure of an LR stimulus."""

    rep_type: Literal["argument_map"] = "argument_map"
    nodes: list[ArgumentNode] = Field(min_length=1)
    edges: list[ArgumentEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _edges_reference_nodes(self) -> ArgumentMapRep:
        ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.from_ not in ids or e.to not in ids:
                raise ValueError(f"edge {e.from_}->{e.to} references unknown node id")
        return self


class PassageParagraph(BaseModel):
    paragraph: int = Field(ge=1)
    role: str
    gist: str


class PassageMapRep(BaseModel):
    """Paragraph-by-paragraph structural outline of an RC passage."""

    rep_type: Literal["passage_map"] = "passage_map"
    paragraphs: list[PassageParagraph] = Field(min_length=1)


Representation = Annotated[
    SequenceRep | GridRep | NotationRep | ArgumentMapRep | PassageMapRep,
    Field(discriminator="rep_type"),
]


# ---------------------------------------------------------------------------
# Guide + step models (spec 041 FR-1)
# ---------------------------------------------------------------------------


class SolveStep(BaseModel):
    kind: StepKind
    title: str
    text: str
    representation: Representation | None = None
    spoiler: bool = False

    @model_validator(mode="after")
    def _answer_steps_are_spoilers(self) -> SolveStep:
        if self.kind == "answer":
            self.spoiler = True
        return self


class SolveGuide(BaseModel):
    question_id: str
    method: str
    steps: list[SolveStep] = Field(min_length=1)
    version: int = 1
    source: str = "original (CC0)"


# ---------------------------------------------------------------------------
# Loader (lazy + cached, mirrors bank.py)
# ---------------------------------------------------------------------------

_GUIDES_FILE = "guides.json"


@lru_cache(maxsize=1)
def load_guides() -> dict[str, SolveGuide]:
    """Load every solve guide, keyed by ``question_id``.

    Fails loudly when a guide targets a question that is not in the bank —
    id drift must surface in tests/CI, never at user request time.
    """
    # Resolve DATA_DIR through the bank module so test sandboxes that
    # monkeypatch ``bank.DATA_DIR`` redirect this loader too.
    path = _bank.DATA_DIR / _GUIDES_FILE
    if not path.is_file():
        return {}
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    guides = [SolveGuide.model_validate(x) for x in raw.get("items", [])]

    bank = _bank.load_bank()
    out: dict[str, SolveGuide] = {}
    for g in guides:
        if g.question_id not in bank:
            raise ValueError(
                f"guide targets unknown question {g.question_id!r} "
                f"(not present in any bank file)"
            )
        if g.question_id in out:
            raise ValueError(f"duplicate guide for question {g.question_id!r}")
        problems = validate_guide_quality(g, bank[g.question_id])
        if problems:
            raise ValueError(
                f"guide for {g.question_id!r} failed quality checks: "
                + "; ".join(problems)
            )
        out[g.question_id] = g
    return out


def reset_guide_cache() -> None:
    """Drop the guide cache. Tests and promotion use this after edits."""
    load_guides.cache_clear()


# ---------------------------------------------------------------------------
# Quality validation (spec 041 FR-11)
# ---------------------------------------------------------------------------

_CHOICE_LABELS = ("A", "B", "C", "D", "E")


def _leak_pattern(correct: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:\banswer\s+is\s+{correct}\b"
        rf"|\bchoice\s+{correct}\b"
        rf"|\b{correct}\s+is\s+(?:the\s+)?(?:correct|right)\b"
        rf"|\bonly\s+{correct}\s+remains\b)",
        re.IGNORECASE,
    )


def _lint_spoiler_discipline(
    guide: SolveGuide, correct: str, problems: list[str]
) -> None:
    """Non-spoiler steps must neither name nor pin the correct choice."""
    leak = _leak_pattern(correct)
    wrong_labels = {label for label in _CHOICE_LABELS if label != correct}
    for i, step in enumerate(guide.steps, start=1):
        if step.spoiler:
            continue
        if leak.search(step.text):
            problems.append(
                f"step {i} names the correct choice before the answer step — "
                "mark it spoiler or reword it"
            )
        # A step that discusses all four wrong choices pins the answer by
        # omission (complete elimination) — it must be a spoiler.
        mentioned = {
            m for m in re.findall(r"\b([A-E])\b", step.text) if m in wrong_labels
        }
        if len(mentioned) >= 4:
            problems.append(
                f"step {i} rules out every wrong choice (complete elimination) "
                "— mark it spoiler"
            )


def _lint_sequence_rep(rep: SequenceRep, i: int, problems: list[str]) -> None:
    slots = set(rep.slots)
    entities = set(rep.entities)
    for slot, entity in rep.placements.items():
        if slot not in slots:
            problems.append(f"step {i} places into unknown slot {slot!r}")
        if entity not in entities:
            problems.append(f"step {i} places unknown entity {entity!r}")
    for slot, excluded in rep.exclusions.items():
        if slot not in slots:
            problems.append(f"step {i} excludes from unknown slot {slot!r}")
        for entity in excluded:
            if entity not in entities:
                problems.append(f"step {i} excludes unknown entity {entity!r}")


def _lint_grid_rep(rep: GridRep, i: int, problems: list[str]) -> None:
    rows, cols = set(rep.rows), set(rep.columns)
    for cell in rep.cells:
        if cell.row not in rows or cell.column not in cols:
            problems.append(
                f"step {i} grid cell ({cell.row!r}, {cell.column!r}) "
                "is outside the declared rows/columns"
            )


def validate_guide_quality(guide: SolveGuide, question: Any) -> list[str]:
    """Content-level lint beyond the Pydantic schema (spec 041 FR-11).

    Runs at every choke point a guide passes through — LLM draft parsing
    (``LSATSolveGuideAuthor``), HITL promotion (``promote_guide_to_bank``)
    and content load (``load_guides``) — so a guide that leaks its answer
    early or contradicts its own board can never serve. ``question`` is the
    bank :class:`~law_ai.lsat.services.bank.Question` the guide targets.
    Returns a list of human-readable problems (empty = clean).
    """
    problems: list[str] = []
    correct = str(question.correct)

    if guide.steps[-1].kind != "answer":
        problems.append("guide must end with an answer step")

    answer_steps = [s for s in guide.steps if s.kind == "answer"]
    if answer_steps and not re.search(rf"\b{correct}\b", answer_steps[-1].text):
        problems.append(f"answer step never names the correct choice {correct!r}")

    _lint_spoiler_discipline(guide, correct, problems)

    for i, step in enumerate(guide.steps, start=1):
        rep = step.representation
        if isinstance(rep, SequenceRep):
            _lint_sequence_rep(rep, i, problems)
        elif isinstance(rep, GridRep):
            _lint_grid_rep(rep, i, problems)
    return problems


# ---------------------------------------------------------------------------
# Public view (spoiler stripping, spec 041 FR-4)
# ---------------------------------------------------------------------------


def public_guide_view(
    guide: SolveGuide, *, include_spoilers: bool = False
) -> dict[str, Any]:
    """Serialize a guide, withholding spoiler-step content unless asked.

    Withheld steps keep their skeleton (``kind``/``title``/``spoiler``) plus
    ``locked: true`` so the UI can honestly show how many steps exist and
    which ones stay closed until the question is graded.
    """
    steps: list[dict[str, Any]] = []
    for step in guide.steps:
        if step.spoiler and not include_spoilers:
            steps.append(
                {
                    "kind": step.kind,
                    "title": step.title,
                    "spoiler": True,
                    "locked": True,
                }
            )
        else:
            payload = step.model_dump(by_alias=True)
            payload["locked"] = False
            steps.append(payload)
    return {
        "question_id": guide.question_id,
        "method": guide.method,
        "version": guide.version,
        "source": guide.source,
        "step_count": len(guide.steps),
        "steps": steps,
    }
