"""Scanned-page intake — a photograph of an LSAT page becomes pending proposals.

The bridge between `ocrmd` (the camera-to-Markdown scanner) and the spec-019 HITL
queue. One call in, one batch of ``pending`` proposals out; nothing here can reach
the live bank, which stays where it has always been — behind a reviewer pressing
approve (constitution §4).

The path is deliberately the *same* path the content factory uses. A question that
walked in off a camera gets no shortcut past the gates a generated one faces:

1. :class:`LSATSourceExtractor` transcribes the page and drops anything it cannot
   ground in the page text;
2. :func:`law_ai.lsat.factory.intake._gate_draft` runs the shared schema, concept-lint
   and near-duplicate gates — the duplicate gate matters more here than anywhere
   else, because rescanning a page is one keystroke and a book has been photographed
   twice before;
3. :func:`law_ai.lsat.services.proposals.record_proposal` persists each survivor with
   the scan's provenance in ``meta``.

**What the provenance is for.** Every proposal from this path names the document,
page and page id it came from, and page ids in ocrmd are the sha256 of the processed
image — so a reviewer holding a draft can always get back to the exact photograph it
was read from. A question you cannot take back to the page is a rumour.
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from pydantic import BaseModel, Field

from law_ai.agents_runtime.crews.lsat_source_extractor import (
    ExtractedQuestion,
    ExtractQuestionsInput,
    LSATSourceExtractor,
)
from law_ai.core.provenance import provenance
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.intake import GateRejection, _dedup_corpus, _gate_draft
from law_ai.lsat.services.bank import Difficulty, Section, load_concepts, load_passages
from law_ai.lsat.services.proposals import record_proposal

logger = logging.getLogger("law_ai.lsat.ocr_intake")

SOURCE_TOOL = "ocrmd"


class ScanProvenance(BaseModel):
    """Where a page came from, as the scanner reported it.

    Every field is optional because the caller is an external tool and a missing
    field must degrade the audit trail, not reject the page. But ``document`` and
    ``page`` together are what make a proposal traceable, so :meth:`is_traceable`
    exists for callers that want to insist on them.
    """

    tool: str = SOURCE_TOOL
    #: The scanner's document slug and page sequence — the human coordinates.
    document: str = ""
    page: int | None = None
    #: sha256 of the *processed* page image: the scanner's own identity for this
    #: page, stable across re-runs and the way back to the exact photograph.
    page_id: str = ""
    page_label: str = ""
    captured_at: str = ""
    #: The scanner's two-reading cross-check, carried through so a reviewer can see
    #: how much the OCR and the vision model disagreed before this text was made.
    ocr_engine: str = ""
    llm_model: str = ""
    agreement: float | None = None
    overlap: float | None = None
    flagged_spans: int | None = None
    status: str = ""
    #: Region of the page, in page fractions, when the operator boxed one question
    #: rather than sending the whole page.
    bbox: list[float] | None = None
    #: A URL the reviewer can open to see the page image, if the scanner is reachable.
    image_url: str = ""

    def is_traceable(self) -> bool:
        return bool(self.document and (self.page is not None or self.page_id))


class IngestScanRequest(BaseModel):
    source_text: str = Field(min_length=1)
    provenance: ScanProvenance = Field(default_factory=ScanProvenance)
    hint: str = ""
    section: Section | None = None
    difficulty: Difficulty | None = None
    max_items: int = Field(default=5, ge=1, le=20)


class IngestScanResult(BaseModel):
    accepted: list[dict[str, Any]] = Field(
        default_factory=list, description="Proposal rows recorded as pending."
    )
    rejected: list[GateRejection] = Field(default_factory=list)
    ungrounded: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Drafts the extractor produced that were not supported by the "
        "page text, and so never reached the gates.",
    )
    notes: str = ""
    trace_id: str | None = None
    model: str = ""
    degraded: bool = False
    extracted: int = 0


class _Target(BaseModel):
    """The duck-typed target ``_gate_draft`` expects.

    The factory builds this from a manifest cell; a scan has no manifest, so the
    target is simply "whatever the page turned out to hold". ``mode="items"`` with
    no ``passage_id`` is the shape that asks the shared gate for section and concept
    checks and nothing else — passage linkage on a scanned RC page is a reviewer's
    job, since the passage is usually on the page before.
    """

    section: Section
    difficulty: Difficulty
    mode: str = "items"
    passage_id: str | None = None


def _meta_for(
    draft: ExtractedQuestion, req: IngestScanRequest, out: Any
) -> dict[str, Any]:
    """Producer lineage for one proposal — the scan, and how it was read."""
    return {
        "producer": "ocr_scan",
        "source": req.provenance.model_dump(exclude_defaults=False),
        "hint": req.hint,
        # The extraction's own honesty signals, kept out of the draft (the bank has
        # no column for them) but in front of whoever reviews it.
        "extraction": {
            "key_source": draft.key_source,
            "explanation_source": draft.explanation_source,
            "grounding": draft.grounding,
            "source_excerpt": draft.source_excerpt,
            "notes": draft.notes,
            "prompt": "lsat_source_extractor/1",
        },
        "agent_notes": out.notes,
    }


def ingest_scan(req: IngestScanRequest) -> IngestScanResult:
    """Extract, gate, and record — the whole scanned-page path.

    Synchronous by design: the caller is an operator who just pressed a button on a
    page they are looking at, and wants to be told what happened to it.
    """
    agent = LSATSourceExtractor()
    out = async_to_sync(agent.run)(
        ExtractQuestionsInput(
            source_text=req.source_text,
            hint=req.hint,
            section=req.section,
            difficulty=req.difficulty,
            max_items=req.max_items,
        ).model_dump()
    )

    result = IngestScanResult(
        ungrounded=list(out.ungrounded),
        notes=out.notes,
        trace_id=out.trace_id,
        model=out.model,
        degraded=out.degraded,
        extracted=len(out.drafts),
    )

    if out.drafts:
        config = FactoryConfig.from_settings()
        catalog = set(load_concepts())
        passages = load_passages()
        # One corpus for the whole batch, extended as drafts are accepted, so two
        # copies of the same question in one request cannot both get through.
        corpus = _dedup_corpus()
        for index, extracted in enumerate(out.drafts):
            target = _Target(section=extracted.section, difficulty=extracted.difficulty)
            draft, rejection = _gate_draft(
                extracted.as_draft().model_dump(),
                index,
                target=target,
                catalog=catalog,
                passages=passages,
                corpus=corpus,
                config=config,
            )
            if draft is None or rejection is not None:
                if rejection is not None:
                    result.rejected.append(rejection)
                continue
            from law_ai.lsat.factory.intake import _tokens  # local: gate-internal

            corpus.append((f"batch-{index}", _tokens(draft.stem)))
            pid = record_proposal(
                draft.model_dump(),
                agent_trace_id=out.trace_id or "",
                model=out.model,
                confidence=extracted.confidence,
                source_concept_ids=draft.concepts,
                meta=_meta_for(extracted, req, out),
                proposal_kind="question",
            )
            result.accepted.append(
                {
                    "id": pid,
                    "section": draft.section,
                    "difficulty": draft.difficulty,
                    "correct": draft.correct,
                    "key_source": extracted.key_source,
                    "grounding": extracted.grounding,
                    "confidence": extracted.confidence,
                    "stem": draft.stem,
                }
            )

    try:
        provenance.log_event(
            "lsat_ocr_intake",
            {
                "tool": req.provenance.tool,
                "document": req.provenance.document,
                "page": req.provenance.page,
                "page_id": req.provenance.page_id,
                "traceable": req.provenance.is_traceable(),
                "hint": req.hint,
                "source_chars": len(req.source_text),
                "extracted": result.extracted,
                "accepted": len(result.accepted),
                "rejected": len(result.rejected),
                "ungrounded": len(result.ungrounded),
                "model": result.model,
                "degraded": result.degraded,
                "agent_trace_id": result.trace_id,
            },
        )
    except Exception:  # pragma: no cover - the audit sink must never fail a scan
        logger.warning("provenance.log_event failed for lsat_ocr_intake", exc_info=True)

    return result
