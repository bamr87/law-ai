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

_PROMPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "agents_runtime" / "prompts"
)

ITEM_TEMPLATE = "lsat_factory_item.v1.md"
PASSAGE_TEMPLATE = "lsat_factory_passage.v1.md"

ITEM_TEMPLATE_VERSION = "lsat_factory_item/1"
PASSAGE_TEMPLATE_VERSION = "lsat_factory_passage/1"


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

    Prefers items matching the target difficulty, then fills with any other
    matches; deterministic (bank id order) so recompiling a plan yields
    byte-identical prompts.
    """
    if k <= 0:
        return []
    arch = get_archetype(target.archetype_id)
    wanted = set(arch.concepts)
    matches = sorted(
        (
            q
            for q in load_bank().values()
            if q.section == target.section and (set(q.concepts) & wanted)
        ),
        key=lambda q: q.id,
    )
    same_diff = [q for q in matches if q.difficulty == target.difficulty]
    rest = [q for q in matches if q.difficulty != target.difficulty]
    return (same_diff + rest)[:k]


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


def compile_prompt(target: GenerationTarget, config: FactoryConfig) -> CompiledPrompt:
    """Render the full generation prompt for one target (see module docstring)."""
    arch = get_archetype(target.archetype_id)
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
