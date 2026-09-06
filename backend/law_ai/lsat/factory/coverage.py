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

from typing import Any, Literal

from pydantic import BaseModel, Field

from law_ai.lsat.factory.config import FactoryConfig, ModelTier, route_tier
from law_ai.lsat.factory.taxonomy import (
    Archetype,
    every_archetype,
    validate_taxonomy,
    writing_archetypes,
)
from law_ai.lsat.services.bank import (
    DIFFICULTY_ORDER,
    Difficulty,
    PassageContext,
    Question,
    Section,
    load_bank,
    load_passages,
)
from law_ai.lsat.services.proposals import gap_analysis
from law_ai.lsat.services.writing import load_writing_prompts

#: Census axis — every band the scale defines, easiest first (spec 047 FR-8).
#: An archetype that declares no weight for a band simply wants nothing there.
DIFFICULTIES: tuple[Difficulty, ...] = DIFFICULTY_ORDER

# Accuracy below this in gap analysis marks a concept as learner-weak; cells
# exercising weak concepts get their priority multiplied by config.gap_boost.
_WEAK_ACCURACY = 0.70

# A target either adds items against an existing passage / standalone stimulus
# ("items") or must author a brand-new passage or game plus its question set
# ("passage_set" — routed to the premium tier by default).
TargetMode = Literal["items", "passage_set", "writing_prompt"]


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


def _effective_bands() -> dict[str, Difficulty]:
    """``question_id → measured band`` for synthesized items with enough grades.

    BL-20260903-14: a band the census counts should be the band learners
    experienced. :mod:`law_ai.lsat.synth.calibrate` returns a row only for a
    schema past its attempts floor, so this is empty until the evidence exists
    and the declared band stands until then.
    """
    try:
        from law_ai.lsat.synth.calibrate import measured_bands

        return measured_bands()
    except Exception:  # pragma: no cover - audit/store issues must not block
        return {}


def _writing_matches(prompt: Any, archetype: Archetype) -> bool:
    """A writing prompt drills a WS archetype when it carries its primary tag."""
    return archetype.concepts[0] in prompt.concepts


def _writing_census() -> dict[tuple[str, Difficulty], int]:
    """Writing prompts per ``(WS archetype, difficulty)`` cell.

    BL-20260831-28: the writing library was invisible to the factory, so the
    coverage loop could grow the MCQ bank and nothing else. Writing prompts
    live in their own store (they produce an essay, not a keyed choice), so
    they are counted from :func:`load_writing_prompts` rather than the bank.
    """
    counts: dict[tuple[str, Difficulty], int] = {}
    ws_archetypes = list(writing_archetypes())
    if not ws_archetypes:  # pragma: no cover - registry always has WS now
        return counts
    try:
        prompts = list(load_writing_prompts().values())
    except Exception:  # pragma: no cover - a broken store must not block planning
        prompts = []
    for arch in ws_archetypes:
        for diff in DIFFICULTIES:
            counts[(arch.id, diff)] = sum(
                1 for p in prompts if p.difficulty == diff and _writing_matches(p, arch)
            )
    return counts


def census() -> dict[tuple[str, Difficulty], int]:
    """Bank items per ``(archetype_id, difficulty)`` cell.

    An item may still count toward several archetypes when it carries several
    primary tags; that is correct — it genuinely drills each such pattern.

    A synthesized item whose schema has enough graded attempts is counted in
    its *measured* band rather than the one it was emitted with.
    """
    counts: dict[tuple[str, Difficulty], int] = {}
    bank = list(load_bank().values())
    measured = _effective_bands()
    banded = [(measured.get(q.id, q.difficulty), q) for q in bank]
    for arch in every_archetype():
        if arch.section == "WS":
            continue  # counted from the writing store, not the bank
        for diff in DIFFICULTIES:
            counts[(arch.id, diff)] = sum(
                1 for band, q in banded if band == diff and _matches(q, arch)
            )
    counts.update(_writing_census())
    return counts


def coverage_matrix(config: FactoryConfig) -> list[CoverageCell]:
    """The census joined with per-cell targets.

    ``config.target_per_cell`` approximates the desired items per cell; each
    archetype's budget is ``target_per_cell x (bands it declares)``, distributed
    across those bands by its exam-frequency weights, so a cell the real exam
    never populates (weight 0.0, or a band the archetype does not span at all)
    wants nothing.

    Scaling the budget by the archetype's *declared* bands rather than by the
    length of :data:`DIFFICULTIES` is what let spec 047 widen the scale from
    three bands to five without inflating every existing archetype's target by
    5/3 overnight.
    """
    counts = census()
    cells: list[CoverageCell] = []
    for arch in every_archetype():
        per_archetype_total = config.target_per_cell * len(arch.difficulty_weights)
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


def _passage_traits(passage: PassageContext) -> str:
    """Searchable text describing what a passage/game can support.

    Prose (title, summary, rules) plus *derived* structural markers, so an
    archetype's ``passage_keyword`` can match a real property of the set and
    not merely a word its author happened to use. Spec 047 FR-9 added
    ``comparative`` this way: a paired Passage A / Passage B set matches
    whether or not its summary says so.
    """
    parts = [passage.title, passage.summary or "", " ".join(passage.rules)]
    if passage.is_comparative:
        parts.append("comparative")
    return " ".join(parts).lower()


def _passage_for(
    archetype: Archetype, *, passage_question_counts: dict[str, int]
) -> tuple[str | None, TargetMode]:
    """Choose a passage strategy for a passage-bound archetype.

    Prefer the existing same-section passage with the fewest linked questions
    (spread coverage); when nothing in the section can serve the archetype —
    no grouping game exists yet, no comparative RC set exists yet — request a
    brand-new ``passage_set``. The filter is the archetype's
    ``passage_keyword`` matched against :func:`_passage_traits`; a grouping
    archetype cannot be served by a sequencing game, and a comparative
    question cannot be served by a single-text passage.
    """
    candidates = [p for p in load_passages().values() if p.section == archetype.section]
    if archetype.passage_keyword:
        needle = archetype.passage_keyword.lower()
        candidates = [p for p in candidates if needle in _passage_traits(p)]
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
    arch_index = {a.id: a for a in every_archetype()}

    for cell in cells:
        arch = arch_index[cell.archetype_id]
        boosted = bool(weak & set(arch.concepts))
        priority = cell.deficit * (config.gap_boost if boosted else 1.0)
        passage_id: str | None = None
        mode: TargetMode = "items"
        if arch.section == "WS":
            # A writing prompt is a whole authored task (issue, positions,
            # perspectives, annotated model essay), so it gets its own mode and
            # is never batched like MCQ items.
            mode = "writing_prompt"
        elif arch.requires_passage:
            passage_id, mode = _passage_for(
                arch, passage_question_counts=passage_counts
            )
        tier = route_tier(cell.difficulty, arch.tier_hint)
        if mode == "passage_set":
            tier = route_tier(cell.difficulty, "premium")
        library = "library has" if mode == "writing_prompt" else "bank has"
        rationale = (
            f"{library} {cell.have}/{cell.want} {cell.difficulty} items for "
            f"{arch.name}"
            + (" — learner-weak concepts" if boosted else "")
            + (
                " — no suitable passage exists; authoring a new set"
                if mode == "passage_set"
                else ""
            )
        )
        # One writing prompt per job: an annotated model essay is the most
        # expensive thing the factory can ask for, and reviewers read them one
        # at a time anyway (NFR-PROV-1 keeps every one HITL-gated).
        count = (
            1 if mode == "writing_prompt" else min(cell.deficit, config.drafts_per_job)
        )
        targets.append(
            GenerationTarget(
                section=arch.section,
                archetype_id=arch.id,
                difficulty=cell.difficulty,
                count=count,
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
