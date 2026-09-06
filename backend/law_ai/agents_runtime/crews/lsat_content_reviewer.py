"""LSATContentReviewer — blind quality review of an LSATContentAuthor draft.

BL-20260527-04. Every draft the authoring pillar produces lands in the HITL
queue unscored, so a reviewer reads a hundred items to find the five that are
broken. This agent reads each draft **blind** (stem + choices, no answer key,
no author explanation) and scores clarity, unintended ambiguity, and whether a
single best answer exists, so borderline items sort to the top of the queue.

Constitution §5: this is a *pre-flag*, never a gate. It cannot approve, reject
or promote anything — ``flagged`` only tells a human where to look first, and
the draft reaches the queue either way.

Mirrors :mod:`lsat_writing_evaluator`: the provider chain via
``law_ai.core.llm`` (never a direct transport), a deterministic offline
fallback at confidence 0.0, and one ``provenance.log_agent_call`` per run.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.agents.lsat_content_reviewer")

PROMPT_VERSION = "lsat_content_reviewer/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_content_reviewer.v1.md"
)

#: Default pre-flag threshold; overridable via ``LSAT_REVIEW_FLAG_THRESHOLD``.
DEFAULT_FLAG_THRESHOLD = 0.6

_MAX_PASSAGE_CHARS = 6_000

_LLM_SYSTEM = (
    "You are an experienced LSAT item reviewer performing a blind quality "
    "review. You never see the answer key. Follow the instructions exactly "
    "and respond with a single JSON object only — no preamble and no markdown "
    "code fences."
)


class ReviewOutput(BaseModel):
    """Advisory quality scores for one drafted item."""

    clarity: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Higher is better: 1.0 = no unintended ambiguity.",
    )
    single_best_answer: float = Field(default=0.0, ge=0.0, le=1.0)
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    flags: list[str] = Field(default_factory=list)
    rationale: str = ""
    flagged: bool = Field(
        default=False,
        description=(
            "True when `overall` is below LSAT_REVIEW_FLAG_THRESHOLD. Advisory "
            "only (constitution §5): the draft still reaches the HITL queue."
        ),
    )
    model: str = "fallback/offline"
    prompt_version: str = PROMPT_VERSION
    degraded: bool = Field(
        default=False,
        description="True when no provider answered and the lint-only fallback ran.",
    )
    latency_ms: float = 0.0
    trace_id: str | None = None


def flag_threshold() -> float:
    try:
        return float(
            getattr(settings, "LSAT_REVIEW_FLAG_THRESHOLD", DEFAULT_FLAG_THRESHOLD)
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return DEFAULT_FLAG_THRESHOLD


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _blind_payload(draft: dict[str, Any], passage: str | None) -> dict[str, Any]:
    """Stem + choices only — the answer key and explanation are withheld."""
    choices = [
        {"label": str(c.get("label", "")), "text": str(c.get("text", ""))}
        for c in (draft.get("choices") or [])
    ]
    return {
        "section": str(draft.get("section") or ""),
        "difficulty": str(draft.get("difficulty") or ""),
        "stem": str(draft.get("stem") or ""),
        "choices": choices,
        "passage": (passage or "")[:_MAX_PASSAGE_CHARS] or None,
    }


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _parse_review(text: str) -> ReviewOutput:
    payload = llm.loads_first_json(text)
    if not isinstance(payload, dict):
        raise ValueError("reviewer response was not a JSON object")
    raw_flags = payload.get("flags") or []
    flags = [str(f).strip()[:60] for f in raw_flags if str(f).strip()][:10]
    return ReviewOutput(
        clarity=_clamp01(payload.get("clarity")),
        ambiguity=_clamp01(payload.get("ambiguity")),
        single_best_answer=_clamp01(payload.get("single_best_answer")),
        overall=_clamp01(payload.get("overall")),
        flags=flags,
        rationale=str(payload.get("rationale") or "").strip()[:1_200],
    )


def _lint_review(draft: dict[str, Any]) -> ReviewOutput:
    """Deterministic offline fallback — mechanical checks, no judgment.

    Scores stay at 0.0 and ``degraded`` is True so nothing reads a lint pass
    as a pedagogical review; the flags are the ones a regex can honestly
    assert.
    """
    flags: list[str] = []
    stem = str(draft.get("stem") or "").strip()
    choices = draft.get("choices") or []
    texts = [str(c.get("text", "")).strip() for c in choices]
    if len(stem) < 20:
        flags.append("ambiguous-stem")
    if len(choices) != 5:
        flags.append("choice-count")
    lengths = [len(t) for t in texts if t]
    if lengths and max(lengths) > 3 * max(1, min(lengths)):
        flags.append("unbalanced-choice-length")
    if len({t.casefold() for t in texts if t}) != len([t for t in texts if t]):
        flags.append("duplicate-choice")
    if str(draft.get("section") or "") == "RC" and not draft.get("passage_id"):
        flags.append("passage-missing")
    return ReviewOutput(
        flags=flags,
        rationale=(
            "No provider was reachable, so this is a mechanical lint only — "
            "clarity, ambiguity and single-best-answer were NOT judged. "
            "Treat the scores as absent, not as zero quality."
        ),
        degraded=True,
        flagged=True,
    )


class LSATContentReviewer:
    """Blind reviewer that pre-flags weak LSATContentAuthor drafts.

    Advisory only: it never approves or rejects. ``human_approval_required``
    stays True so the registry surfaces that a human still decides.
    """

    name = "LSATContentReviewer"
    description = (
        "Reads one drafted LSAT item blind (no answer key) and scores clarity, "
        "unintended ambiguity, and whether a single best answer exists, so a "
        "human reviewer sees borderline drafts first. Never approves or "
        "rejects — pre-flag only (constitution §5)."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> ReviewOutput:
        draft = input_data.get("draft")
        if not isinstance(draft, dict):
            raise ValueError("LSATContentReviewer requires input_data['draft']")
        passage = input_data.get("passage")
        started = time.perf_counter()

        full_prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(
                _blind_payload(draft, str(passage) if passage else None), indent=2
            )
            + "\n```\n"
        )

        try:
            result = await llm.agenerate(
                full_prompt,
                system=_LLM_SYSTEM,
                json_mode=True,
                agent="lsat_content_reviewer",
            )
            review = _parse_review(result.text)
            review.model = result.model_label
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATContentReviewer falling back to lint-only: %s", exc)
            review = _lint_review(draft)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATContentReviewer unexpected error: %s", exc, exc_info=True
            )
            review = _lint_review(draft)

        if not review.degraded:
            review.flagged = review.overall < flag_threshold()
        review.latency_ms = (time.perf_counter() - started) * 1000.0
        review.trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "section": draft.get("section"),
                "difficulty": draft.get("difficulty"),
                "stem": str(draft.get("stem") or "")[:200],
                "prompt_version": PROMPT_VERSION,
            },
            output_data=review.model_dump(),
            model=review.model,
            latency_ms=review.latency_ms,
            confidence=0.0 if review.degraded else review.overall,
        )
        return review


async def review_drafts(
    drafts: list[dict[str, Any]],
) -> list[dict[str, Any] | None]:
    """Blind-review each draft, returning one review dict (or ``None``) per draft.

    The batch entry point both the autonomy cycle and
    ``POST /api/lsat/proposals/generate`` use. Off when
    ``LSAT_CONTENT_REVIEW=false`` (it doubles model calls per draft) and never
    fatal: a reviewer failure yields ``None`` for that draft so the proposal is
    still filed. Constitution §5 — the review pre-flags, it never rejects.
    """
    if not getattr(settings, "LSAT_CONTENT_REVIEW", True):
        return [None] * len(drafts)

    reviewer = LSATContentReviewer()
    out: list[dict[str, Any] | None] = []
    for draft in drafts:
        try:
            review = await reviewer.run({"draft": draft})
            out.append(review.model_dump())
        except Exception as exc:
            logger.warning("lsat content review failed: %s", exc, exc_info=True)
            out.append(None)
    return out
