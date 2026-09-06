"""Blueprint compiler — generation targets → few-shot, archetype-grounded prompts.

Spec 024 FR-4. A compiled prompt stacks, in order:

1. the versioned base template (item or passage mode, loaded from
   ``agents_runtime/prompts`` — never inlined);
2. the archetype's item-writing guidance (the taxonomy's craft knowledge);
3. up to K real bank exemplars of the same archetype, answer keys included —
   these are *authoring references* that anchor style, length, and distractor
   craft (the few-shot core of "based on LSAT patterns");
4. the section-scoped concept catalog the model may tag from;
5. the existing passage/game context when writing against one;
6. the machine-readable request (count, difficulty, archetype, mode).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.taxonomy import get_archetype
from law_ai.lsat.services.bank import (
    Question,
    load_bank,
    load_concepts,
    load_passages,
)
from law_ai.lsat.services.writing import load_writing_prompts, load_writing_rubrics

_PROMPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "agents_runtime" / "prompts"
)

ITEM_TEMPLATE = "lsat_factory_item.v1.md"
PASSAGE_TEMPLATE = "lsat_factory_passage.v1.md"
WRITING_TEMPLATE = "lsat_factory_writing.v1.md"

ITEM_TEMPLATE_VERSION = "lsat_factory_item/1"
PASSAGE_TEMPLATE_VERSION = "lsat_factory_passage/1"
WRITING_TEMPLATE_VERSION = "lsat_factory_writing/1"

#: Rubric a factory-drafted writing prompt is written against. The library
#: ships exactly one; when that changes this becomes a target field.
DEFAULT_RUBRIC_ID = "argumentative-writing-v1"

#: Characters of an exemplar model essay kept as a register reference. The
#: whole essay would dominate the prompt without teaching anything more.
_EXEMPLAR_ESSAY_CHARS = 700


class CompiledPrompt(BaseModel):
    """A fully rendered generation prompt plus its template lineage."""

    template_version: str
    text: str


def _load_template(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.is_file():  # pragma: no cover - prompts ship with the code
        raise FileNotFoundError(f"missing prompt template: {path}")
    return path.read_text(encoding="utf-8")


def _serialize_exemplar(q: Question) -> dict[str, Any]:
    """Bank item → authoring reference (id/source stripped, key kept)."""
    return {
        "difficulty": q.difficulty,
        "stem": q.stem,
        "choices": [{"label": c.label, "text": c.text} for c in q.choices],
        "correct": q.correct,
        "explanation": q.explanation,
        "concepts": list(q.concepts),
    }


def select_exemplars(target: GenerationTarget, k: int) -> list[Question]:
    """Same-archetype bank items to embed as few-shot references.

    Bank items carry concepts, not an archetype id, so the match is by concept
    overlap — and *how well* an item matches has to be ranked or the few-shot
    block teaches the wrong pattern (BL-20260901-02). An archetype's first
    concept is its primary tag (see :class:`~law_ai.lsat.factory.taxonomy.
    Archetype`), so an item carrying it is a true instance of the pattern and
    outranks one that merely shares a broad secondary concept; ties go to the
    item with more shared concepts, then to the target difficulty, then to bank
    id order, which keeps recompiling a plan byte-identical.
    """
    if k <= 0:
        return []
    arch = get_archetype(target.archetype_id)
    primary = arch.concepts[0]
    wanted = set(arch.concepts)

    def rank(q: Question) -> tuple[int, int, int, int, str]:
        concepts = set(q.concepts)
        return (
            # BL-20260905-54: an item stamped with this archetype is an exact
            # instance of the pattern; the concept proxy below is a guess.
            0 if q.archetype == target.archetype_id else 1,
            0 if primary in concepts else 1,
            -len(concepts & wanted),
            0 if q.difficulty == target.difficulty else 1,
            q.id,
        )

    matches = [
        q
        for q in load_bank().values()
        if q.section == target.section
        and (q.archetype == target.archetype_id or (set(q.concepts) & wanted))
    ]
    return sorted(matches, key=rank)[:k]


def _concept_slice(target: GenerationTarget) -> list[dict[str, str]]:
    """Section-scoped concept catalog (id/name/summary) for tagging."""
    catalog = load_concepts()
    rows = [
        {"id": c.id, "name": c.name, "summary": c.summary}
        for c in catalog.values()
        if target.section in c.sections
    ]
    # Target concepts first so the model reaches for the right tags.
    wanted = set(target.concepts)
    rows.sort(key=lambda r: (0 if r["id"] in wanted else 1, r["id"]))
    return rows


def _writing_exemplar() -> dict[str, Any] | None:
    """One existing writing prompt as a shape reference (essay truncated)."""
    prompts = sorted(load_writing_prompts().values(), key=lambda p: p.id)
    if not prompts:
        return None
    ref = prompts[0]
    return {
        "title": ref.title,
        "issue": ref.issue,
        "context": ref.context,
        "positions": [p.model_dump() for p in ref.positions],
        "perspectives": [p.model_dump() for p in ref.perspectives],
        "task": ref.task,
        "concepts": list(ref.concepts),
        "model_response": {
            "position_id": ref.model_response.position_id,
            "thesis": ref.model_response.thesis,
            "essay_excerpt": ref.model_response.essay[:_EXEMPLAR_ESSAY_CHARS],
            "annotations": [a.model_dump() for a in ref.model_response.annotations],
        },
        "self_check": [c.model_dump() for c in ref.self_check],
    }


def _rubric_block() -> str:
    """The rubric criteria a drafted prompt must reference by id."""
    rubrics = load_writing_rubrics()
    rubric = rubrics.get(DEFAULT_RUBRIC_ID) or next(iter(rubrics.values()), None)
    if rubric is None:  # pragma: no cover - the library ships one
        return ""
    return (
        "\n## Rubric (reference these criterion ids ONLY)\n\n```json\n"
        + json.dumps(
            {
                "id": rubric.id,
                "criteria": [
                    {"id": c.id, "name": c.name, "description": c.description}
                    for c in rubric.criteria
                ],
                "bands": [{"level": b.level, "label": b.label} for b in rubric.bands],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n```\n"
    )


def _compile_writing_prompt(target: GenerationTarget, arch: Any) -> CompiledPrompt:
    """Render a WS authoring prompt (BL-20260831-28).

    Same stack as the item blueprint — template, archetype guidance, one
    exemplar, the taggable concepts, the machine-readable request — but the
    exemplar is a writing prompt and the rubric travels with it, because every
    self-check and annotation must name a criterion the rubric defines.
    """
    parts: list[str] = [_load_template(WRITING_TEMPLATE)]
    parts.append(
        "\n## Target archetype\n\n"
        f"- **id**: {arch.id}\n"
        f"- **name**: {arch.name}\n"
        f"- **section**: WS\n"
        f"- **guidance**: {arch.guidance}\n"
    )
    exemplar = _writing_exemplar()
    if exemplar is not None:
        parts.append(
            "\n## Exemplar (shape and register reference from the live "
            "library — invent entirely new content)\n\n```json\n"
            + json.dumps(exemplar, indent=2, ensure_ascii=False)
            + "\n```\n"
        )
    parts.append(_rubric_block())
    parts.append(
        "\n## Concept catalog (tag drafts ONLY with these ids)\n\n```json\n"
        + json.dumps(_concept_slice(target), indent=2, ensure_ascii=False)
        + "\n```\n"
    )
    parts.append(
        "\n## Request\n\n```json\n"
        + json.dumps(
            {
                "section": "WS",
                "archetype_id": target.archetype_id,
                "difficulty": target.difficulty,
                "count": target.count,
                "rubric_id": DEFAULT_RUBRIC_ID,
                "target_concepts": list(target.concepts),
                "mode": "writing_prompt",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n```\n"
    )
    return CompiledPrompt(
        template_version=WRITING_TEMPLATE_VERSION, text="".join(parts)
    )


def compile_prompt(target: GenerationTarget, config: FactoryConfig) -> CompiledPrompt:
    """Render the full generation prompt for one target (see module docstring)."""
    arch = get_archetype(target.archetype_id)
    if target.mode == "writing_prompt":
        return _compile_writing_prompt(target, arch)
    is_passage_set = target.mode == "passage_set"
    template_name = PASSAGE_TEMPLATE if is_passage_set else ITEM_TEMPLATE
    template_version = (
        PASSAGE_TEMPLATE_VERSION if is_passage_set else ITEM_TEMPLATE_VERSION
    )

    parts: list[str] = [_load_template(template_name)]

    parts.append(
        "\n## Target archetype\n\n"
        f"- **id**: {arch.id}\n"
        f"- **name**: {arch.name}\n"
        f"- **section**: {arch.section}\n"
        f"- **guidance**: {arch.guidance}\n"
    )

    exemplars = select_exemplars(target, config.exemplar_count)
    if exemplars:
        parts.append(
            "\n## Exemplars (style references from the live bank — do NOT "
            "copy or paraphrase their content)\n\n```json\n"
            + json.dumps(
                [_serialize_exemplar(q) for q in exemplars],
                indent=2,
                ensure_ascii=False,
            )
            + "\n```\n"
        )

    if is_passage_set:
        # Give a same-section context as a *format* reference where one exists.
        fmt = [p for p in load_passages().values() if p.section == target.section]
        if fmt:
            ref = sorted(fmt, key=lambda p: p.id)[0]
            parts.append(
                "\n## Format reference (existing context — match the shape, "
                "invent entirely new content)\n\n```json\n"
                + json.dumps(
                    {
                        "section": ref.section,
                        "title": ref.title,
                        "summary": ref.summary,
                        "passage": ref.passage,
                        "setup": ref.setup,
                        "rules": list(ref.rules),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n```\n"
            )
    elif target.passage_id:
        passage = load_passages().get(target.passage_id)
        if passage is not None:
            parts.append(
                "\n## Passage / game context (write questions against THIS)\n\n"
                "```json\n"
                + json.dumps(
                    {
                        "id": passage.id,
                        "title": passage.title,
                        "passage": passage.passage,
                        "setup": passage.setup,
                        "rules": list(passage.rules),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n```\n"
            )

    parts.append(
        "\n## Concept catalog (tag drafts ONLY with these ids)\n\n```json\n"
        + json.dumps(_concept_slice(target), indent=2, ensure_ascii=False)
        + "\n```\n"
    )

    request: dict[str, Any] = {
        "section": target.section,
        "archetype_id": target.archetype_id,
        "difficulty": target.difficulty,
        "count": target.count,
        "target_concepts": list(target.concepts),
        "mode": target.mode,
    }
    if target.passage_id:
        request["passage_id"] = target.passage_id
    parts.append(
        "\n## Request\n\n```json\n"
        + json.dumps(request, indent=2, ensure_ascii=False)
        + "\n```\n"
    )

    return CompiledPrompt(template_version=template_version, text="".join(parts))
