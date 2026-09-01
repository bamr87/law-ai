"""``lsat_export`` — snapshot the LSAT module into a static-site artifact.

Spec 025 FR-1/FR-2. Writes ``content.json`` — the complete, HITL-approved
LSAT content module (sections, concepts, passages, questions **including
answer keys and explanations**) — for the serverless practice app under
``frontend/public/lsat-practice/``.

Spec 046 adds ``guides``: the spec 045 solve guides are hand-authored static
data, so the static export can render the same hint carousel and diagrams the
API-backed lab does. Spoiler steps ship too — the site already carries answer
keys in order to grade offline — and the *client* keeps them locked until the
question is graded, mirroring ``public_guide_view``.

Spec 047 adds ``writing_prompts`` and ``writing_rubrics``. The whole point of
shipping the rubric and the annotated model response is that a learner can
score their own draft with no model call and no network (spec 047 FR-3,
NFR-OFFLINE-1), so the model responses ship in full; the *client* keeps them
locked until the learner submits, mirroring the guide spoiler contract.

Everything is loaded through the canonical Pydantic loaders in
:mod:`law_ai.lsat.services.bank`, so only loader-valid content can ship.
Ordering is stable (sections LR/RC/LG; everything else by id) so re-exports
of an unchanged bank are byte-identical apart from ``generated_at`` — the
property the root-suite drift gate (tests/test_lsat_site.py) relies on.

    make lsat-export
    # or: make manage CMD='lsat_export --pretty'
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from law_ai.lsat.services.bank import (
    load_bank,
    load_concepts,
    load_passages,
    load_sections,
)
from law_ai.lsat.services.guides import load_guides
from law_ai.lsat.services.writing import load_writing_prompts, load_writing_rubrics

SCHEMA_VERSION = 2

_SECTION_ORDER = ("LR", "RC", "LG", "WS")

_DEFAULT_OUT = "var/lsat_site"


def build_content() -> dict[str, Any]:
    """Assemble the full content payload (deterministic apart from timestamp)."""
    sections = load_sections()
    concepts = load_concepts()
    passages = load_passages()
    bank = load_bank()

    questions = [
        bank[qid].model_dump(mode="json")
        for qid in sorted(
            bank,
            key=lambda q: (_SECTION_ORDER.index(bank[q].section), q),
        )
    ]
    rubrics = load_writing_rubrics()
    prompts = load_writing_prompts()
    counts: dict[str, int] = {s: 0 for s in _SECTION_ORDER}
    for q in bank.values():
        counts[q.section] = counts.get(q.section, 0) + 1

    # Only guides whose question actually shipped, sorted for byte-stable
    # re-exports (the tests/test_lsat_site.py drift gate depends on it).
    guides = load_guides()
    guide_payload = [
        guides[qid].model_dump(mode="json", by_alias=True)
        for qid in sorted(guides)
        if qid in bank
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": {
            "total": len(questions),
            **counts,
            "guides": len(guide_payload),
            "writing_prompts": len(prompts),
        },
        "sections": [
            sections[code].model_dump(mode="json")
            for code in _SECTION_ORDER
            if code in sections
        ],
        "concepts": [concepts[cid].model_dump(mode="json") for cid in sorted(concepts)],
        "passages": [passages[pid].model_dump(mode="json") for pid in sorted(passages)],
        "questions": questions,
        "guides": guide_payload,
        "writing_rubrics": [
            rubrics[rid].model_dump(mode="json") for rid in sorted(rubrics)
        ],
        "writing_prompts": [
            prompts[pid].model_dump(mode="json") for pid in sorted(prompts)
        ],
    }


class Command(BaseCommand):
    help = "Export the LSAT content module as a static-site artifact (spec 025)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--out",
            default=_DEFAULT_OUT,
            help=f"Output directory (default: {_DEFAULT_OUT}).",
        )
        parser.add_argument(
            "--pretty",
            action="store_true",
            help="Indent the JSON (bigger file, diff-friendly).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        out_dir = Path(str(opts["out"]))
        out_dir.mkdir(parents=True, exist_ok=True)
        content = build_content()
        path = out_dir / "content.json"
        indent = 2 if opts.get("pretty") else None
        path.write_text(
            json.dumps(content, indent=indent, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        counts = content["counts"]
        self.stdout.write(
            self.style.SUCCESS(
                f"exported {counts['total']} questions "
                f"(LR {counts['LR']} / RC {counts['RC']} / LG {counts['LG']}), "
                f"{len(content['passages'])} passages, "
                f"{len(content['concepts'])} concepts, "
                f"{counts['writing_prompts']} writing prompts → {path}"
            )
        )
