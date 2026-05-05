"""LSAT AI Tutor (spec 005 refactor — 2026-05-03).

Provides personalized, on-demand explanations for any LSAT question in the
bank. Routes through Ollama when reachable (constitution §1: open-source,
local-first), and falls back to a deterministic, source-grounded synthesis
when the model is unreachable so the feature never hard-fails.

Every invocation is recorded via :mod:`app.core.audit_store` so it surfaces
in the Agent Ops dashboard, satisfying the audit-grade gate (constitution
§3) and matching the LR Tutor backlog item BL-20260429-18.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from lexgraph.core import audit_jsonl as audit_store
from lexgraph.core.settings_proxy import settings_proxy as settings
from lexgraph.lsat.services.bank import (
    ChoiceLabel,
    Concept,
    PassageContext,
    Question,
    load_concepts,
    load_passages,
)

logger = logging.getLogger("lexgraph.lsat.tutor")

PROMPT_VERSION = "lsat-tutor/1"

# Soft cap so a long passage doesn't blow the context window of small models.
_MAX_PASSAGE_CHARS = 4_000


class TutorRequest(BaseModel):
    question_id: str
    user_choice: ChoiceLabel | None = Field(
        default=None,
        description="The answer the learner picked. Optional — omit for a generic walkthrough.",
    )
    user_question: str | None = Field(
        default=None,
        max_length=2_000,
        description="Free-form follow-up the learner wants the tutor to address.",
    )


class TutorReference(BaseModel):
    title: str
    url: str | None = None
    note: str | None = None


class TutorResponse(BaseModel):
    question_id: str
    user_choice: ChoiceLabel | None
    correct_choice: ChoiceLabel
    is_correct: bool | None = Field(
        default=None,
        description="None when ``user_choice`` was omitted.",
    )
    explanation: str = Field(
        ..., description="Short answer-key rationale shipped with the bank."
    )
    coaching: str = Field(
        ..., description="Personalized walkthrough (LLM or fallback)."
    )
    next_steps: list[str] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    references: list[TutorReference] = Field(default_factory=list)
    model: str = Field(
        ..., description="Identifier of the model that produced ``coaching``."
    )
    used_llm: bool = Field(..., description="True iff Ollama generated the coaching.")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    requires_human_review: bool = Field(default=False)
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _PromptCtx:
    question: Question
    passage: PassageContext | None
    concepts: list[Concept]


def _build_prompt(
    ctx: _PromptCtx, user_choice: ChoiceLabel | None, user_question: str | None
) -> str:
    q = ctx.question
    parts: list[str] = [
        "You are an LSAT tutor. Be concise (≤ 200 words), structured, and honest.",
        "ALWAYS reference the answer key as authoritative; do not invent a different correct choice.",
        f"Section: {q.section}.  Difficulty: {q.difficulty}.",
    ]
    if ctx.passage:
        passage_text = ctx.passage.passage or ctx.passage.setup or ""
        if passage_text:
            parts.append(f"Passage / setup:\n{passage_text[:_MAX_PASSAGE_CHARS]}")
        if ctx.passage.rules:
            parts.append("Rules:\n- " + "\n- ".join(ctx.passage.rules))
    parts.append(f"Question: {q.stem}")
    parts.append("Choices:\n" + "\n".join(f"  {c.label}. {c.text}" for c in q.choices))
    parts.append(f"Authoritative correct choice: {q.correct}")
    parts.append(f"Answer-key rationale: {q.explanation}")
    if ctx.concepts:
        names = ", ".join(c.name for c in ctx.concepts)
        parts.append(f"Relevant concepts: {names}")
    if user_choice:
        parts.append(
            f"Learner picked: {user_choice} ({'correct' if user_choice == q.correct else 'incorrect'})."
        )
    else:
        parts.append("Learner has not yet chosen an answer.")
    if user_question:
        parts.append(f"Learner asks: {user_question}")
    parts.append(
        "Respond as JSON only with keys: coaching (string, ≤200 words, addressed to the learner), "
        "next_steps (array of 1-3 short imperative strings). Do not include any other keys or prose."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Ollama client (lightweight; avoids langchain dependency)
# ---------------------------------------------------------------------------


async def _ollama_generate(prompt: str, *, model: str) -> str:
    """Call Ollama's /api/generate and return the raw response text.

    Raises ``httpx.HTTPError`` / ``asyncio.TimeoutError`` on failure so the
    caller can fall back gracefully.
    """
    url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
        "format": "json",
    }
    timeout = httpx.Timeout(settings.OLLAMA_REQUEST_TIMEOUT_S)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return str(data.get("response") or "").strip()


def _parse_llm_payload(text: str) -> tuple[str, list[str]]:
    """Best-effort parse of the JSON-only contract returned by the prompt."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Treat the whole response as the coaching paragraph.
        return text.strip()[:1_500], []
    coaching = str(obj.get("coaching") or "").strip()
    raw_steps = obj.get("next_steps") or []
    steps = [str(s).strip() for s in raw_steps if str(s).strip()][:3]
    return coaching[:1_500], steps


# ---------------------------------------------------------------------------
# Deterministic offline fallback
# ---------------------------------------------------------------------------


def _fallback_coaching(
    q: Question,
    user_choice: ChoiceLabel | None,
    user_question: str | None,
    concepts: list[Concept],
) -> tuple[str, list[str]]:
    """Synthesize a usable explanation without calling any model."""
    parts: list[str] = []
    if user_choice is None:
        parts.append(f"You haven't picked yet. The answer key is {q.correct}.")
    elif user_choice == q.correct:
        parts.append(f"Correct — the key is {q.correct}.")
    else:
        parts.append(
            f"Your pick was {user_choice}; the answer key is {q.correct}. "
            "Re-read the stem and the rationale below side-by-side to see what tipped the scale."
        )
    parts.append(q.explanation)
    if concepts:
        bullets = "; ".join(f"{c.name} — {c.summary}" for c in concepts[:3])
        parts.append(f"Concepts in play: {bullets}")
    if user_question:
        parts.append(
            "On your follow-up: the offline fallback can't tailor a fresh answer, but "
            "the rationale above plus the linked concept entries should cover most "
            "variants of your question. Re-ask once the local Ollama model is reachable."
        )
    coaching = " ".join(parts)
    next_steps = [
        (
            f"Review the {concepts[0].name} concept entry."
            if concepts
            else "Re-read the stem aloud and restate the conclusion in your own words."
        ),
        "Diagram any conditional indicators ('if', 'only if', 'unless').",
        "Try one more question at the same difficulty to lock in the pattern.",
    ]
    return coaching, next_steps[:3]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def tutor(req: TutorRequest, q: Question) -> TutorResponse:
    """Produce a tutor response for ``q``, mixed with optional learner input.

    Always returns a populated response — falls back to an offline summary if
    the LLM is unreachable. Records an audit event regardless of path.
    """
    import time

    started = time.perf_counter()

    passages = load_passages()
    concepts_by_id = load_concepts()
    passage = passages.get(q.passage_id) if q.passage_id else None
    concept_entries = [
        concepts_by_id[cid] for cid in q.concepts if cid in concepts_by_id
    ]

    prompt = _build_prompt(
        _PromptCtx(q, passage, concept_entries), req.user_choice, req.user_question
    )

    used_llm = False
    coaching = ""
    next_steps: list[str] = []
    model_used = "fallback/offline"
    confidence = 0.55

    try:
        raw = await _ollama_generate(prompt, model=settings.OLLAMA_DEFAULT_MODEL)
        coaching, next_steps = _parse_llm_payload(raw)
        if coaching:
            used_llm = True
            model_used = settings.OLLAMA_DEFAULT_MODEL
            # Heuristic confidence: longer, structured responses tend to be better.
            confidence = 0.85 if next_steps and len(coaching) > 80 else 0.7
    except (TimeoutError, httpx.HTTPError, OSError) as exc:
        logger.info("LSAT tutor falling back to offline path: %s", exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LSAT tutor unexpected error: %s", exc, exc_info=True)

    if not coaching:
        coaching, next_steps = _fallback_coaching(
            q, req.user_choice, req.user_question, concept_entries
        )

    refs = [TutorReference(title=r.title, url=r.url, note=r.note) for r in q.references]
    # Promote first concept reference if the question itself ships none.
    if not refs and concept_entries:
        for c in concept_entries:
            for r in c.references:
                refs.append(TutorReference(title=r.title, url=r.url, note=r.note))
                if len(refs) >= 3:
                    break
            if len(refs) >= 3:
                break

    is_correct = (req.user_choice == q.correct) if req.user_choice else None
    requires_human_review = used_llm and confidence < 0.7

    latency_ms = (time.perf_counter() - started) * 1000.0

    response = TutorResponse(
        question_id=q.id,
        user_choice=req.user_choice,
        correct_choice=q.correct,
        is_correct=is_correct,
        explanation=q.explanation,
        coaching=coaching,
        next_steps=next_steps,
        concepts=concept_entries,
        references=refs,
        model=model_used,
        used_llm=used_llm,
        confidence=confidence,
        requires_human_review=requires_human_review,
        latency_ms=round(latency_ms, 2),
    )

    _audit_event(req, q, response)
    return response


def _audit_event(req: TutorRequest, q: Question, resp: TutorResponse) -> None:
    """Append a dashboard-visible record. Failures are swallowed by audit_store."""
    event: dict[str, Any] = {
        "type": "lsat_tutor",
        "agent": "LsatTutor",
        "prompt_version": PROMPT_VERSION,
        "question_id": q.id,
        "section": q.section,
        "user_choice": req.user_choice,
        "is_correct": resp.is_correct,
        "model": resp.model,
        "used_llm": resp.used_llm,
        "confidence": resp.confidence,
        "latency_ms": resp.latency_ms,
        "requires_human_review": resp.requires_human_review,
    }
    audit_store.record(event)
