"""Independent answer cross-check (spec 041 FR-14).

Asks the provider chain to solve a bank question BLIND — the prompt carries
the stem, passage, and choices, but never the answer key or the rationale —
then compares the model's pick against the key. Agreement is corroboration;
disagreement flags either a weak model solve or a mis-keyed question, and is
marked ``requires_human_review`` so the question set itself can be audited
for accuracy (constitution §13: consensus is reported with its source named,
never laundered as verification).

Verdicts from real model calls are cached (spec 041 FR-13 pattern) so
repeat cross-checks of the same question are free; ``refresh=True``
re-solves. Every invocation writes an ``lsat_cross_check`` audit event.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code, llm, xai
from law_ai.core.provenance import provenance
from law_ai.lsat.services import llm_cache
from law_ai.lsat.services.bank import (
    ChoiceLabel,
    Question,
    load_passages,
)

logger = logging.getLogger("law_ai.lsat.crosscheck")

PROMPT_VERSION = "lsat-cross-check/1"

_MAX_PASSAGE_CHARS = 4_000

_LLM_SYSTEM = (
    "You are an expert LSAT solver. Solve the question from scratch. "
    "Respond with JSON only — no preamble and no markdown code fences."
)


class CrossCheckResult(BaseModel):
    question_id: str
    bank_choice: ChoiceLabel = Field(
        ..., description="The answer key shipped with the bank."
    )
    model_choice: ChoiceLabel | None = Field(
        default=None,
        description="The chain's independent pick; None when no provider "
        "was reachable or the response was unparseable.",
    )
    agree: bool | None = Field(
        default=None,
        description="model_choice == bank_choice; None when no independent "
        "solve was produced.",
    )
    rationale: str = Field(
        default="", description="The model's own reasoning for its pick."
    )
    model: str
    used_llm: bool
    cached: bool = False
    requires_human_review: bool = Field(
        default=False,
        description="True on disagreement — a human should re-verify the "
        "answer key (or the solve).",
    )
    latency_ms: float = 0.0


def _build_prompt(q: Question) -> str:
    """Blind prompt: no answer key, no rationale, no learner context."""
    parts: list[str] = [
        f"Section: {q.section}.  Difficulty: {q.difficulty}.",
    ]
    passage = load_passages().get(q.passage_id) if q.passage_id else None
    if passage:
        text = passage.passage or passage.setup or ""
        if text:
            parts.append(f"Passage / setup:\n{text[:_MAX_PASSAGE_CHARS]}")
        if passage.rules:
            parts.append("Rules:\n- " + "\n- ".join(passage.rules))
    parts.append(f"Question: {q.stem}")
    parts.append("Choices:\n" + "\n".join(f"  {c.label}. {c.text}" for c in q.choices))
    parts.append(
        "Solve the question yourself. Respond as JSON only with keys: "
        'choice (one of "A","B","C","D","E") and rationale (string, ≤120 words '
        "explaining your pick). Do not include any other keys or prose."
    )
    return "\n\n".join(parts)


def _parse_verdict(text: str) -> tuple[ChoiceLabel | None, str]:
    try:
        obj = llm.loads_first_json(text)
    except json.JSONDecodeError:
        return None, ""
    raw = str(obj.get("choice") or "").strip().upper()[:1]
    choice: ChoiceLabel | None = (
        raw if raw in ("A", "B", "C", "D", "E") else None  # type: ignore[assignment]
    )
    rationale = str(obj.get("rationale") or "").strip()[:1_200]
    return choice, rationale


async def cross_check(q: Question, *, refresh: bool = False) -> CrossCheckResult:
    """Independently solve ``q`` and compare against its answer key."""
    started = time.perf_counter()
    key = llm_cache.cache_key(
        "crosscheck", {"question_id": q.id, "prompt_version": PROMPT_VERSION}
    )
    if not refresh:
        hit = llm_cache.get(key)
        if hit is not None:
            cached: CrossCheckResult | None
            try:
                cached = CrossCheckResult.model_validate(
                    {**hit, "cached": True, "latency_ms": 0.0}
                )
            except Exception:  # malformed row (old schema) — re-solve
                cached = None
            if cached is not None:
                _audit_event(cached)
                return cached

    model_choice: ChoiceLabel | None = None
    rationale = ""
    model_used = "fallback/offline"
    used_llm = False
    try:
        llm_result = await llm.agenerate(
            _build_prompt(q),
            system=_LLM_SYSTEM,
            json_mode=True,
            agent="lsat_cross_check",
            # A learner is waiting on this panel, so it takes the faster Grok
            # id when one is configured (BL-20260905-11).
            models=xai.interactive_overrides(),
        )
        model_choice, rationale = _parse_verdict(llm_result.text)
        if model_choice is not None:
            used_llm = True
            model_used = llm_result.model_label
    except (
        TimeoutError,
        httpx.HTTPError,
        OSError,
        claude_code.ClaudeCodeUnavailableError,
        llm.LLMUnavailableError,
    ) as exc:
        logger.info("cross-check falling back to unavailable: %s", exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("cross-check unexpected error: %s", exc, exc_info=True)

    agree = (model_choice == q.correct) if model_choice is not None else None
    result = CrossCheckResult(
        question_id=q.id,
        bank_choice=q.correct,
        model_choice=model_choice,
        agree=agree,
        rationale=(
            rationale
            if used_llm
            else "No provider reachable — cross-check unavailable; try again later."
        ),
        model=model_used,
        used_llm=used_llm,
        requires_human_review=agree is False,
        latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
    )

    if used_llm:
        try:
            llm_cache.put(key, result.model_dump())
        except Exception:  # pragma: no cover - cache failure must not block UX
            logger.warning("llm_cache.put failed for lsat_cross_check", exc_info=True)

    _audit_event(result)
    return result


def _audit_event(result: CrossCheckResult) -> None:
    """Append one ``lsat_cross_check`` event per invocation.

    Goes through :func:`provenance.log_event` (BL-20260527-06) so every fresh
    verdict lands in ``AuditEvent`` as well as the JSONL store: the audit log
    is the per-question time series :mod:`law_ai.lsat.services.regression`
    reads, since the response cache only keeps the latest verdict.
    """
    provenance.log_event(
        "lsat_cross_check",
        {
            "prompt_version": PROMPT_VERSION,
            "question_id": result.question_id,
            "bank_choice": result.bank_choice,
            "model_choice": result.model_choice,
            "agree": result.agree,
            "model": result.model,
            "used_llm": result.used_llm,
            "cached": result.cached,
            "requires_human_review": result.requires_human_review,
        },
    )
