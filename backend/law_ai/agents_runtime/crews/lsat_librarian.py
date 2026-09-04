"""LSATLibrarian — reviews, corrects and expands the LSAT knowledge library.

Spec 048 FR-15/FR-16. The content factory (spec 024) grows the *question*
bank and the spec 047 judge scores drafts; nothing until now maintained a body
of explanatory prose. This agent does one of three jobs per run:

``review``
    Read one article and report located defects — an inaccurate claim about the
    exam, a checkable claim carrying no reference, a gap, a passage that will be
    misread, a missing cross-reference.
``correct``
    Given one finding, propose replacement Markdown for the affected passage
    only.
``expand``
    Given a declared gap, draft a new section or a whole new article body.

Mirrors :mod:`lsat_solve_guide_author` throughout: the provider chain via
``law_ai.core.llm`` and never a direct transport, a deterministic offline
fallback at confidence 0.0, one ``provenance.log_agent_call`` per run
including on the degraded path, and ``human_approval_required = True``.

**This agent never writes to ``data/library/``.** Its output is persisted by
the caller as a proposal and reaches a learner only when a reviewer promotes
it (spec 048 AC-10). That separation is the whole safety story for an agent
whose failure mode is confidently describing a section format LSAC changed.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.lsat.services import bank as _bank
from law_ai.lsat.services import library as _library

logger = logging.getLogger("law_ai.agents.lsat_librarian")

PROMPT_VERSION = "lsat_librarian/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_librarian.v1.md"
)

# The model sees the article as Markdown, not as compiled blocks: patching one
# section of prose is the thing it is good at, and the compiled tree is a
# derived form it would only have to un-derive.
_MAX_ARTICLE_CHARS = 24_000

_LLM_SYSTEM = (
    "You are an LSAT curriculum editor maintaining a knowledge library. "
    "Follow the instructions exactly and respond with a single JSON object "
    "only — no preamble and no markdown code fences. Never invent facts about "
    "the exam's structure; report an unverifiable claim rather than asserting "
    "a correction."
)

LibrarianAction = Literal["review", "correct", "expand"]

FindingSeverity = Literal["high", "med", "low"]
FindingCategory = Literal[
    "accuracy", "verify", "gap", "clarity", "structure", "link", "scope"
]


class LibraryFinding(BaseModel):
    """One located defect. ``anchor`` and ``quote`` are what make it actionable."""

    severity: FindingSeverity
    category: FindingCategory
    anchor: str | None = None
    quote: str | None = None
    problem: str
    suggestion: str | None = None


class LibrarianInput(BaseModel):
    action: LibrarianAction = "review"
    article_id: str | None = Field(
        default=None,
        description="Target article. Required for review and correct; optional "
        "on expand (absent = draft a new article).",
    )
    finding: LibraryFinding | None = Field(
        default=None, description="The defect to fix. Required for correct."
    )
    gap: str | None = Field(
        default=None, description="What is missing. Required for expand."
    )


class LibrarianOutput(BaseModel):
    action: LibrarianAction
    article_id: str | None = None
    summary: str
    findings: list[LibraryFinding] = Field(default_factory=list)
    proposed_markdown: str | None = None
    model: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    latency_ms: float = 0.0
    degraded: bool = Field(
        False,
        description="True when every provider failed and the fallback was used.",
    )
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _article_source(article_id: str) -> str:
    """The article's on-disk Markdown, which is what the model edits."""
    path = _library._library_dir() / f"{article_id}.md"
    if not path.is_file():
        raise KeyError(f"no source file for article {article_id!r}")
    source: str = path.read_text(encoding="utf-8")
    return source[:_MAX_ARTICLE_CHARS]


def _build_user_payload(inp: LibrarianInput) -> dict[str, Any]:
    articles = _library.load_library()
    payload: dict[str, Any] = {
        "action": inp.action,
        # Bounding the id lists is what keeps the model from inventing a
        # cross-reference that fails the load.
        "known_ids": {
            "articles": sorted(articles),
            "concepts": sorted(_bank.load_concepts()),
        },
    }
    if inp.article_id:
        article = articles[inp.article_id]
        payload["article"] = {
            "id": article.id,
            "title": article.title,
            "kind": article.kind,
            "summary": article.summary,
            "markdown": _article_source(article.id),
        }
    if inp.finding is not None:
        payload["finding"] = inp.finding.model_dump()
    if inp.gap:
        payload["gap"] = inp.gap
    return payload


def _parse_response(
    raw: str, *, inp: LibrarianInput
) -> tuple[str, list[LibraryFinding], str | None]:
    obj = llm.loads_first_json(raw)
    if not isinstance(obj, dict):
        raise ValueError("LLM response is not a JSON object")
    summary = str(obj.get("summary") or "").strip()
    if not summary:
        raise ValueError("LLM response missing 'summary'")
    findings = [
        LibraryFinding.model_validate(f)
        for f in obj.get("findings") or []
        if isinstance(f, dict)
    ]
    proposed = obj.get("proposed_markdown")
    markdown = (
        str(proposed).strip()
        if isinstance(proposed, str) and proposed.strip()
        else None
    )
    if inp.action in ("correct", "expand") and markdown is None:
        raise ValueError(f"action {inp.action!r} produced no proposed_markdown")
    return summary, findings, markdown


def _fallback(inp: LibrarianInput) -> tuple[str, list[LibraryFinding], str | None]:
    """Deterministic placeholder when every provider fails.

    Confidence 0.0 and an unmistakable offline label so a reviewer always
    rejects it; it exists to keep the cycle auditable, not to ship content.
    """
    summary = (
        "[OFFLINE FALLBACK — no LLM provider reachable] No review was performed. "
        "This result MUST be rejected by a reviewer."
    )
    if inp.action == "review":
        return summary, [], None
    return (
        summary,
        [],
        "## Offline fallback\n\n[OFFLINE FALLBACK — no LLM provider reachable] "
        "Author this section by hand. This draft MUST be rejected.\n",
    )


class LSATLibrarian:
    """Reviews, corrects and expands knowledge-library articles (spec 048 FR-15)."""

    name = "LSATLibrarian"
    description = (
        "Reviews LSAT knowledge-library articles for accuracy, gaps, clarity "
        "and missing cross-references, and drafts corrections or expansions. "
        "Every output is HITL-gated; nothing it writes reaches a learner "
        "without explicit reviewer approval, and it never edits content files."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> LibrarianOutput:
        inp = LibrarianInput.model_validate(input_data)

        articles = _library.load_library()
        if inp.action in ("review", "correct") and not inp.article_id:
            raise ValueError(f"action {inp.action!r} requires an article_id")
        if inp.article_id and inp.article_id not in articles:
            raise KeyError(f"unknown article {inp.article_id!r}")
        if inp.action == "correct" and inp.finding is None:
            raise ValueError("action 'correct' requires a finding")
        if inp.action == "expand" and not inp.gap:
            raise ValueError("action 'expand' requires a gap description")

        started = time.perf_counter()
        prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(_build_user_payload(inp), indent=2)
            + "\n```\n"
        )

        degraded = False
        model_used = "fallback/offline"
        confidence = 0.0
        try:
            result = await llm.agenerate(
                prompt, system=_LLM_SYSTEM, agent="lsat_librarian"
            )
            model_used = result.model_label
            summary, findings, markdown = _parse_response(result.text, inp=inp)
            # Deliberately below the guide author's 0.7: prose about exam
            # structure is harder to verify mechanically than a solve guide,
            # whose steps are checked against a known answer key.
            confidence = 0.6
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATLibrarian falling back to offline: %s", exc)
            degraded = True
            model_used = "fallback/offline"
            summary, findings, markdown = _fallback(inp)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LSATLibrarian unexpected error: %s", exc, exc_info=True)
            degraded = True
            model_used = "fallback/offline"
            summary, findings, markdown = _fallback(inp)

        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={"action": inp.action, "article_id": inp.article_id},
            output_data={
                "finding_count": len(findings),
                "has_draft": markdown is not None,
                "model": model_used,
                "confidence": confidence,
                "degraded": degraded,
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=confidence,
            sources=[],
        )

        return LibrarianOutput(
            action=inp.action,
            article_id=inp.article_id,
            summary=summary,
            findings=findings,
            proposed_markdown=markdown,
            model=model_used,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
