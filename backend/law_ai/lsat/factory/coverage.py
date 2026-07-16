"""Coverage census + generation-target planning.

Spec 024 FR-3. Answers "what should the factory build next?" by combining:

* a **census** of live bank items per ``(archetype, difficulty)`` cell — an
  item counts toward an archetype when it carries at least one of the
  archetype's concept tags;
* per-archetype **exam-frequency weights** (the taxonomy's
  ``difficulty_weights``) that shape how many items each cell *should* hold;
* learner **gap analysis** (``lsat_grade`` audit events) that boosts cells
  whose concepts learners are getting wrong.

The output is a deterministic, priority-ranked list of
:class:`GenerationTarget` rows, each small enough to become one manifest job.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from law_ai.lsat.factory.config import FactoryConfig, ModelTier, route_tier
from law_ai.lsat.factory.taxonomy import (
    Archetype,
    all_archetypes,
    validate_taxonomy,
)
from law_ai.lsat.services.bank import (
    Difficulty,
    Question,
    Section,
    load_bank,
    load_passages,
)
from law_ai.lsat.services.proposals import gap_analysis

DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "med", "hard")

# Accuracy below this in gap analysis marks a concept as learner-weak; cells
# exercising weak concepts get their priority multiplied by config.gap_boost.
_WEAK_ACCURACY = 0.70

# A target either adds items against an existing passage / standalone stimulus
# ("items") or must author a brand-new passage or game plus its question set
# ("passage_set" — routed to the premium tier by default).
TargetMode = Literal["items", "passage_set"]


class CoverageCell(BaseModel):
    """Census row for one ``(archetype x difficulty)`` cell."""

    section: Section
    archetype_id: str
    difficulty: Difficulty
    have: int = Field(ge=0)
    want: int = Field(ge=0)

    @property
    def deficit(self) -> int:
        return max(0, self.want - self.have)


class GenerationTarget(BaseModel):
    """One prioritized unit of generation work (→ one manifest job)."""

    section: Section
    archetype_id: str
    difficulty: Difficulty
    count: int = Field(ge=1, le=10)
    concepts: list[str]
    mode: TargetMode = "items"
    passage_id: str | None = Field(
        default=None,
        description="Existing passage/game to write against (RC/LG 'items' "
        "mode); None for standalone LR items or a new passage_set.",
    )
    tier: ModelTier
    priority: float = Field(ge=0.0)
    rationale: str


def _matches(question: Question, archetype: Archetype) -> bool:
    # Primary-concept matching (the taxonomy's documented contract): an item
    # drills an archetype only when it carries the archetype's *first* concept
    # tag. Any-overlap would let e.g. sequencing must-be-true items masquerade
    # as grouping-game coverage via the shared secondary tag.
    return archetype.concepts[0] in question.concepts


def census() -> dict[tuple[str, Difficulty], int]:
    """Bank items per ``(archetype_id, difficulty)`` cell.

    An item may still count toward several archetypes when it carries several
    primary tags; that is correct — it genuinely drills each such pattern.
    """
    counts: dict[tuple[str, Difficulty], int] = {}
    bank = list(load_bank().values())
    for arch in all_archetypes():
        for diff in DIFFICULTIES:
            counts[(arch.id, diff)] = sum(
                1 for q in bank if q.difficulty == diff and _matches(q, arch)
            )
    return counts


def coverage_matrix(config: FactoryConfig) -> list[CoverageCell]:
    """The census joined with per-cell targets.

    ``config.target_per_cell`` approximates the desired items per cell; each
    archetype's total budget (``3 x target_per_cell``) is distributed across
    difficulties by its exam-frequency weights, so a cell the real exam never
    populates (weight 0.0) wants nothing.
    """
    counts = census()
    cells: list[CoverageCell] = []
    per_archetype_total = config.target_per_cell * len(DIFFICULTIES)
    for arch in all_archetypes():
        for diff in DIFFICULTIES:
            weight = arch.difficulty_weights.get(diff, 0.0)
            want = round(per_archetype_total * weight)
            cells.append(
                CoverageCell(
                    section=arch.section,
                    archetype_id=arch.id,
                    difficulty=diff,
                    have=counts[(arch.id, diff)],
                    want=want,
                )
            )
    return cells


def _weak_concepts() -> set[str]:
    """Concept ids learners are currently weak on (per audit gap analysis)."""
    try:
        rows = gap_analysis()
    except Exception:  # pragma: no cover - audit store issues must not block
        return set()
    return {
        str(r["concept"])
        for r in rows
        if isinstance(r.get("accuracy"), (int, float))
        and float(r["accuracy"]) < _WEAK_ACCURACY
    }


def _passage_for(
    archetype: Archetype, *, passage_question_counts: dict[str, int]
) -> tuple[str | None, TargetMode]:
    """Choose a passage strategy for a passage-bound archetype.

    Prefer the existing same-section passage with the fewest linked questions
    (spread coverage); when the section has no passage at all — e.g. no
    grouping game exists yet — request a brand-new ``passage_set``.
    """
    candidates = [p for p in load_passages().values() if p.section == archetype.section]
    # A grouping archetype can't be served by a sequencing game: new set.
    if archetype.id == "lg-grouping":
        grouping_ready = [
            p for p in candidates if "group" in ((p.summary or "") + p.title).lower()
        ]
        candidates = grouping_ready
    if not candidates:
        return None, "passage_set"
    best = min(
        candidates,
        key=lambda p: (passage_question_counts.get(p.id, 0), p.id),
    )
    return best.id, "items"


def plan_targets(config: FactoryConfig) -> list[GenerationTarget]:
    """Rank under-covered cells into concrete generation targets.

    Deterministic for a fixed bank + audit state: cells sort by boosted
    deficit (descending), then archetype id, then difficulty order. Capped at
    ``config.max_jobs`` rows of at most ``config.drafts_per_job`` items each.
    """
    validate_taxonomy()
    weak = _weak_concepts()
    passage_counts: dict[str, int] = {}
    for q in load_bank().values():
        if q.passage_id:
            passage_counts[q.passage_id] = passage_counts.get(q.passage_id, 0) + 1

    targets: list[GenerationTarget] = []
    diff_order = {d: i for i, d in enumerate(DIFFICULTIES)}
    cells = [c for c in coverage_matrix(config) if c.deficit > 0]
    arch_index = {a.id: a for a in all_archetypes()}

    for cell in cells:
        arch = arch_index[cell.archetype_id]
        boosted = bool(weak & set(arch.concepts))
        priority = cell.deficit * (config.gap_boost if boosted else 1.0)
        passage_id: str | None = None
        mode: TargetMode = "items"
        if arch.requires_passage:
            passage_id, mode = _passage_for(
                arch, passage_question_counts=passage_counts
            )
        tier = route_tier(cell.difficulty, arch.tier_hint)
        if mode == "passage_set":
            tier = route_tier(cell.difficulty, "premium")
        rationale = (
            f"bank has {cell.have}/{cell.want} {cell.difficulty} items for "
            f"{arch.name}"
            + (" — learner-weak concepts" if boosted else "")
            + (
                " — no suitable passage exists; authoring a new set"
                if mode == "passage_set"
                else ""
            )
        )
        targets.append(
            GenerationTarget(
                section=arch.section,
                archetype_id=arch.id,
                difficulty=cell.difficulty,
                count=min(cell.deficit, config.drafts_per_job),
                concepts=list(arch.concepts),
                mode=mode,
                passage_id=passage_id,
                tier=tier,
                priority=priority,
                rationale=rationale,
            )
        )

    targets.sort(key=lambda t: (-t.priority, t.archetype_id, diff_order[t.difficulty]))
    return targets[: config.max_jobs]
