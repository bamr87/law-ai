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
from pydantic import BaseModel, Field, model_validator

from law_ai.agents_runtime.crews.lsat_source_extractor import (
    ExtractedQuestion,
    ExtractQuestionsInput,
    LSATSourceExtractor,
)
from law_ai.core.provenance import provenance
from law_ai.ingestionapp.services.ocrmd_plugin import (
    Envelope,
    descriptor,
    is_envelope,
    option,
)
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.intake import GateRejection, _dedup_corpus, _gate_draft
from law_ai.lsat.services.bank import (
    DIFFICULTY_ORDER,
    MCQ_SECTIONS,
    Difficulty,
    Section,
    load_concepts,
    load_passages,
)
from law_ai.lsat.services.proposals import record_proposal

logger = logging.getLogger("law_ai.lsat.ocr_intake")

SOURCE_TOOL = "ocrmd"

#: The sink descriptor (spec 053): what ocrmd probes with ``GET`` before it draws its Send
#: panel, so the operator sees this door's options with their real choices instead of
#: typing field names from memory.
INTAKE_DESCRIPTOR = descriptor(
    "Law AI — LSAT question",
    "Extracts the LSAT questions printed on the page and queues them for a human "
    "reviewer. The text travels; the photograph does not.",
    [
        option(
            "hint",
            "string",
            label="which item",
            help_="e.g. 'question 15'; blank takes every complete one",
        ),
        option(
            "section",
            "enum",
            label="section",
            choices=list(MCQ_SECTIONS),
            help_="a steer, not a claim — the model reads the page",
        ),
        option(
            "difficulty",
            "enum",
            label="difficulty",
            choices=list(DIFFICULTY_ORDER),
        ),
        option("max_items", "integer", label="max items", default=5),
    ],
)


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
    # --- carried by the sink envelope (spec 053) ------------------------------------
    tool_version: str = ""
    #: Disagreement marks still open in the text that was sent (the scanner strips
    #: nothing; the extractor does, see ``clean_page_text``).
    unresolved: int | None = None
    #: The page in the scanner's own UI, for a reviewer who wants the context.
    page_url: str = ""
    #: The book, as the scanner's catalogue names it.
    document_title: str = ""

    def is_traceable(self) -> bool:
        return bool(self.document and (self.page is not None or self.page_id))


class IngestScanRequest(BaseModel):
    source_text: str = Field(min_length=1)
    provenance: ScanProvenance = Field(default_factory=ScanProvenance)
    hint: str = ""
    section: Section | None = None
    difficulty: Difficulty | None = None
    max_items: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="before")
    @classmethod
    def _accept_envelope(cls, data: Any) -> Any:
        """The ocrmd envelope — ``text``, ``provenance``, ``document``, ``options`` —
        mapped onto the fields this door has taken since it opened. The legacy shape
        (``source_text`` + top-level ``hint``/``section``/``difficulty``) still works,
        so nothing that posted here before spec 053 has to change.
        """
        if not isinstance(data, dict) or not is_envelope(data):
            return data
        env = Envelope.model_validate(data)
        opts = env.options
        prov = env.provenance.model_dump()
        prov["document_title"] = env.document.title or ""
        out: dict[str, Any] = {
            "source_text": env.text,
            "provenance": prov,
            "hint": str(opts.get("hint") or ""),
        }
        for key in ("section", "difficulty", "max_items"):
            if opts.get(key) not in (None, ""):
                out[key] = opts[key]
        return out

    @model_validator(mode="after")
    def _only_keyed_sections(self) -> IngestScanRequest:
        """WS is an essay task with no answer key: it can never be the target of this
        door, and saying so here is a 422 with the field named rather than a 500."""
        if self.section is not None and self.section not in MCQ_SECTIONS:
            raise ValueError(
                f"section {self.section!r} has no multiple-choice form "
                f"(expected one of {list(MCQ_SECTIONS)})"
            )
        return self


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
    # --- the answer in the sink contract's terms (spec 053) ---------------------------
    summary: str = ""
    items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="One row per accepted draft: id, title (the stem), detail, status.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Ungrounded and gate-rejected drafts, one sentence each.",
    )


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


def _summarise(result: IngestScanResult) -> None:
    """Fill ``summary``/``items``/``warnings`` from the gate outcome — one line a person
    (or the scanner's UI) can act on, then one row per draft they can find in the queue.
    """
    if result.accepted:
        keys = ", ".join(str(a.get("correct")) for a in result.accepted)
        result.summary = (
            f"{len(result.accepted)} question(s) queued for review (key {keys})"
        )
    elif result.ungrounded:
        result.summary = (
            f"nothing queued: {len(result.ungrounded)} draft(s) were not supported by "
            "the page text"
        )
    elif result.rejected:
        reasons = ", ".join(sorted({str(r.reason) for r in result.rejected}))
        result.summary = (
            f"nothing queued: {len(result.rejected)} draft(s) rejected ({reasons})"
        )
    elif result.degraded:
        result.summary = "nothing queued: no model answered"
    else:
        result.summary = "nothing queued: no complete question was found on this page"
    result.items = [
        {
            "id": a.get("id"),
            "title": str(a.get("stem") or "")[:120],
            "detail": (
                f"{a.get('section')}/{a.get('difficulty')} · key {a.get('correct')} "
                f"({a.get('key_source')}) · grounding {a.get('grounding')} · "
                f"confidence {a.get('confidence')}"
            ),
            "status": "pending",
        }
        for a in result.accepted
    ]
    result.warnings = [
        f"dropped, not supported by the page text (grounding {u.get('grounding')}): "
        f"{str(u.get('source_excerpt'))[:80]}"
        for u in result.ungrounded
    ] + [
        f"rejected at the {r.reason} gate: {str(r.detail)[:120]}"
        for r in result.rejected
    ]


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

    _summarise(result)
    return result
