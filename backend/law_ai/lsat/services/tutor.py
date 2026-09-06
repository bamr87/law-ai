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
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.telemetry import phoenix_trace_url as _phoenix_trace_url
from law_ai.core import claude_code, llm, xai
from law_ai.lsat.services import llm_cache
from law_ai.lsat.services.bank import (
    ChoiceLabel,
    Concept,
    PassageContext,
    Question,
    load_concepts,
    load_passages,
)

logger = logging.getLogger("law_ai.lsat.tutor")

#: Recorded on every ``lsat_tutor`` audit event, on the ``llm_call``
#: provenance event, and in the response-cache key, so a prompt change is
#: visible in the audit trail and never serves a stale walkthrough. Matches
#: the file name in ``agents_runtime/prompts/`` (BL-20260503-01).
PROMPT_VERSION = "lsat_tutor/1"

# Soft cap so a long passage doesn't blow the context window of small models.
_MAX_PASSAGE_CHARS = 4_000


class TutorTrace(BaseModel):
    """What the learner actually did on this attempt (BL-20260429-18).

    The tutor's distinguishing promise is coaching addressed to *this*
    reasoning, not a generic rationale — "you ruled out B and D, so the split
    you cared about was ..." rather than "the answer is C because ...". None of
    it is inferable server-side: elimination, hint reveals and time live in the
    lab, so the client sends them or the tutor works without them.

    Every field is optional. A client that captures none of this gets exactly
    the behaviour it had before the field existed.
    """

    eliminated: list[ChoiceLabel] = Field(
        default_factory=list,
        max_length=5,
        description="Choices the learner ruled out before answering.",
    )
    hints_used: int = Field(
        default=0,
        ge=0,
        le=50,
        description="Solve-assist steps revealed on this question (spec 045).",
    )
    seconds_on_question: float | None = Field(
        default=None,
        ge=0.0,
        le=24 * 3600.0,
        description="Wall-clock seconds spent before asking.",
    )
    prior_choices: list[ChoiceLabel] = Field(
        default_factory=list,
        max_length=5,
        description="Answers tried on earlier attempts at this question.",
    )

    def is_empty(self) -> bool:
        """True when the client sent a trace but captured nothing in it."""
        return not (
            self.eliminated
            or self.hints_used
            or self.seconds_on_question
            or self.prior_choices
        )

    def signature(self) -> str:
        """A coarse cache discriminator for this attempt shape.

        Coarse on purpose: keying on the exact second would make every
        walkthrough a cache miss, while ignoring the trace entirely would serve
        a learner who eliminated nothing the coaching written for one who
        eliminated three. Elimination and prior picks are exact (they change
        what the coaching must address); time is bucketed to the minute and
        hint count is used as-is.
        """
        minutes = (
            int(self.seconds_on_question // 60)
            if self.seconds_on_question is not None
            else -1
        )
        return (
            f"e={''.join(sorted(self.eliminated))};"
            f"h={self.hints_used};m={minutes};"
            f"p={''.join(self.prior_choices)}"
        )


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
    refresh: bool = Field(
        default=False,
        description="Bypass the walkthrough cache and force a fresh model call "
        "(spec 041 FR-13).",
    )
    trace: TutorTrace | None = Field(
        default=None,
        description=(
            "What the learner did on this attempt — eliminations, hints "
            "revealed, time spent, earlier picks (BL-20260429-18). Optional; "
            "without it the coaching addresses only the answer they chose."
        ),
    )
    stream_tokens: bool = Field(
        default=False,
        description=(
            "Stream the coaching token by token over ``stream_id`` "
            "(BL-20260503-03). Requires ``stream_id``; without one it is "
            "ignored, since there is nowhere to send the deltas. The streamed "
            "variant asks the model for prose rather than JSON — a partial "
            "JSON object is not a document — so its wording differs slightly "
            "from the buffered one."
        ),
    )
    stream_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
        description=(
            "Client-chosen WebSocket correlation id (BL-20260811-15). "
            "Subscribe to /ws/agents/<stream_id> BEFORE posting and the tutor "
            "publishes its progress there — a cache hit, which tier it is "
            "waiting on, a fallback — instead of leaving the learner watching "
            "a spinner for the length of a hosted call."
        ),
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
    cached: bool = Field(
        default=False,
        description="True when this walkthrough was served from the response "
        "cache instead of a fresh model call (spec 041 FR-13).",
    )
    trace_id: str | None = Field(
        default=None,
        description=(
            "OTEL trace this walkthrough was produced under (BL-20260503-06). "
            "None when telemetry is disabled, which is the local-first default."
        ),
    )
    phoenix_trace_url: str | None = Field(
        default=None,
        description=(
            "Deep link to the trace in the configured viewer, mirroring the "
            "analysis path (BL-20260502-05). There is deliberately no "
            "``langgraph_thread_id`` beside it: the tutor calls the provider "
            "chain directly rather than running a LangGraph graph, so there is "
            "no checkpointed thread to resume or to name."
        ),
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _PromptCtx:
    question: Question
    passage: PassageContext | None
    concepts: list[Concept]


#: Sentinel the streamed contract puts before its next-steps list. The
#: coaching is everything before it, so a client rendering deltas can show
#: prose the moment it arrives and still get structured next steps at the end
#: (BL-20260503-03).
NEXT_STEPS_MARKER = "NEXT STEPS:"


#: The versioned prompt file. Wording lives here, not in Python, so a change
#: is a reviewable diff tied to ``PROMPT_VERSION`` (BL-20260503-01).
PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "agents_runtime"
    / "prompts"
    / "lsat_tutor.v1.md"
)

_SECTION_RE = re.compile(r"^<!--\s*section:\s*([\w.]+)\s*-->$", re.MULTILINE)


@lru_cache(maxsize=1)
def _prompt_sections() -> dict[str, str]:
    """The named sections of :data:`PROMPT_PATH`, cached for the process.

    Split on the ``<!-- section: name -->`` markers so one versioned file can
    hold the user template and both system steers — one artefact per prompt
    version is what makes drift auditable at all.
    """
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    text = PROMPT_PATH.read_text(encoding="utf-8")
    pieces = _SECTION_RE.split(text)
    # pieces[0] is the file's preamble; the rest alternate name, body.
    return {
        name: body.strip("\n")
        for name, body in zip(pieces[1::2], pieces[2::2], strict=True)
    }


def _section(name: str) -> str:
    try:
        return _prompt_sections()[name]
    except KeyError as exc:  # pragma: no cover - a malformed prompt file
        raise KeyError(f"{PROMPT_PATH} has no section {name!r}") from exc


def _block(text: str) -> str:
    """Wrap one optional prompt block in the blank lines around it, or drop it."""
    return f"\n{text}\n" if text else ""


def _passage_block(ctx: _PromptCtx) -> str:
    if ctx.passage is None:
        return ""
    parts: list[str] = []
    passage_text = ctx.passage.passage or ctx.passage.setup or ""
    if passage_text:
        parts.append(f"Passage / setup:\n{passage_text[:_MAX_PASSAGE_CHARS]}")
    if ctx.passage.rules:
        parts.append("Rules:\n- " + "\n- ".join(ctx.passage.rules))
    return _block("\n\n".join(parts))


def _trace_block(trace: TutorTrace | None) -> str:
    """Render the learner's attempt trace, or nothing when there is none."""
    if trace is None or trace.is_empty():
        return ""
    lines: list[str] = ["What the learner did on this attempt:"]
    if trace.eliminated:
        lines.append(f"- Ruled out: {', '.join(trace.eliminated)}")
    if trace.prior_choices:
        lines.append(f"- Previously answered: {', '.join(trace.prior_choices)}")
    if trace.hints_used:
        lines.append(f"- Revealed {trace.hints_used} solve-assist step(s)")
    if trace.seconds_on_question:
        lines.append(f"- Spent about {int(trace.seconds_on_question)}s on it")
    lines.append(
        "Address this reasoning directly: say where it went right or wrong "
        "rather than restating the rationale from scratch."
    )
    return _block("\n".join(lines))


def _learner_block(q: Question, user_choice: ChoiceLabel | None) -> str:
    if user_choice is None:
        return _block("Learner has not yet chosen an answer.")
    verdict = "correct" if user_choice == q.correct else "incorrect"
    return _block(f"Learner picked: {user_choice} ({verdict}).")


def _build_prompt(
    ctx: _PromptCtx,
    user_choice: ChoiceLabel | None,
    user_question: str | None,
    *,
    streamed: bool = False,
    trace: TutorTrace | None = None,
) -> str:
    """Render the versioned template for one question.

    ``streamed`` swaps only the output contract: JSON cannot be rendered token
    by token — a partial object is not a document — so the streamed variant
    asks for prose first and puts the structure on the last line, where it
    costs nothing to wait for (BL-20260503-03).
    """
    q = ctx.question
    concepts = ", ".join(c.name for c in ctx.concepts)
    contract = "contract.streamed" if streamed else "contract.buffered"
    return _section("user").format(
        section=q.section,
        difficulty=q.difficulty,
        passage_block=_passage_block(ctx),
        question=q.stem,
        choices="\n".join(f"  {c.label}. {c.text}" for c in q.choices),
        correct=q.correct,
        explanation=q.explanation,
        concepts_block=_block(f"Relevant concepts: {concepts}" if concepts else ""),
        learner_block=_learner_block(q, user_choice),
        trace_block=_trace_block(trace),
        follow_up_block=_block(
            f"Learner asks: {user_question}" if user_question else ""
        ),
        output_contract=_section(contract),
    )


def _parse_stream_payload(text: str) -> tuple[str, list[str]]:
    """Split the streamed contract into ``(coaching, next_steps)``.

    A reply that never reached the marker still yields usable coaching — the
    prose is the part the learner reads — so a model that ignored the last
    instruction degrades to "no next steps" rather than to nothing.
    """
    body, _, tail = text.partition(NEXT_STEPS_MARKER)
    steps = [s.strip() for s in tail.split("|") if s.strip()][:3]
    return body.strip()[:1_500], steps


# The system steers live in the versioned prompt file alongside the user
# template, so one file is the whole prompt for one version. (Ollama's
# /api/generate has no system role, so its instructions ride in the body too.)


# ---------------------------------------------------------------------------
# Progress streaming (BL-20260811-15)
# ---------------------------------------------------------------------------


async def _emit(req: TutorRequest, payload: dict[str, Any]) -> None:
    """Publish one progress event when the caller asked for a stream.

    A no-op without ``stream_id`` — the REST contract is unchanged for every
    existing client — and never fatal: the helper swallows channel-layer
    failures so a Redis outage cannot cost a learner their walkthrough.
    """
    if not req.stream_id:
        return
    from law_ai.agentsapi.streaming import emit_stream_event

    await emit_stream_event(req.stream_id, payload, source="lsat_tutor")


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------


async def _generate_coaching(prompt: str) -> tuple[str, str]:
    """Generate raw coaching text through the shared provider chain (spec 034).

    Claude first, the Anthropic API key second, local Ollama last. Returns
    ``(raw_text, model_label)``; raises when every provider fails so the caller
    can fall back to the deterministic offline path rather than inventing an
    answer (constitution §13).
    """
    result = await llm.agenerate(
        prompt,
        system=_section("system.buffered"),
        json_mode=True,
        agent="lsat_tutor",
        prompt_id="lsat_tutor",
        prompt_version=PROMPT_VERSION,
        # A learner is waiting on this one, so pin the faster Grok variant if
        # the operator configured one; blank leaves every tier alone
        # (BL-20260905-11).
        models=xai.interactive_overrides(),
    )
    return result.text, result.model_label


def _parse_llm_payload(text: str) -> tuple[str, list[str]]:
    """Best-effort parse of the JSON-only contract returned by the prompt."""
    try:
        obj = llm.loads_first_json(text)
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


def _trace_sentence(q: Question, trace: TutorTrace | None) -> str | None:
    """One sentence the offline path can say about *this* attempt.

    The fallback has no model, but it does have the trace — and naming what the
    learner actually did is most of what makes coaching feel addressed to them
    (BL-20260429-18).
    """
    if trace is None or trace.is_empty():
        return None
    notes: list[str] = []
    if trace.eliminated:
        ruled_out = ", ".join(trace.eliminated)
        if q.correct in trace.eliminated:
            notes.append(
                f"You ruled out {ruled_out} — but {q.correct} is the key, so "
                "the reason you eliminated it is the thing to re-examine"
            )
        else:
            notes.append(f"You ruled out {ruled_out}, which was sound")
    if trace.prior_choices:
        notes.append(f"you had already tried {', '.join(trace.prior_choices)}")
    if trace.hints_used:
        notes.append(f"you revealed {trace.hints_used} solve-assist step(s)")
    if trace.seconds_on_question and trace.seconds_on_question >= 60:
        notes.append(f"you spent about {int(trace.seconds_on_question // 60)} min here")
    return f"{'; '.join(notes)}." if notes else None


def _fallback_coaching(
    q: Question,
    user_choice: ChoiceLabel | None,
    user_question: str | None,
    concepts: list[Concept],
    trace: TutorTrace | None = None,
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
    trace_note = _trace_sentence(q, trace)
    if trace_note:
        parts.append(trace_note)
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


def _cache_lookup(req: TutorRequest, q: Question) -> tuple[str, TutorResponse | None]:
    """Spec 041 FR-13: key this request shape and return any stored walkthrough.

    The key embeds PROMPT_VERSION so prompt bumps invalidate naturally;
    ``req.refresh`` skips the read (the key is still returned for the write).
    A malformed stored row (old schema) reads as a miss and is regenerated.
    """
    key = llm_cache.cache_key(
        "tutor",
        {
            "question_id": q.id,
            "user_choice": req.user_choice,
            "user_question": req.user_question or "",
            "prompt_version": PROMPT_VERSION,
            # The streamed variant asks for prose, not JSON, so its output is
            # a different document; sharing a key would serve one contract's
            # walkthrough to the other's caller (BL-20260503-03).
            "streamed": bool(req.stream_tokens and req.stream_id),
            # BL-20260429-18: the trace changes what the coaching has to
            # address, so two attempts that reasoned differently must not share
            # a walkthrough. Coarse (see TutorTrace.signature) so the cache
            # still earns its keep.
            "trace": req.trace.signature() if req.trace else "",
        },
    )
    if req.refresh:
        return key, None
    hit = llm_cache.get(key)
    if hit is None:
        return key, None
    try:
        return key, TutorResponse.model_validate(
            {**hit, "cached": True, "latency_ms": 0.0}
        )
    except Exception:
        return key, None


@dataclass(slots=True)
class _Coaching:
    """One chain attempt's outcome, or the offline defaults when it failed."""

    coaching: str = ""
    next_steps: list[str] = field(default_factory=list)
    model: str = "fallback/offline"
    confidence: float = 0.55
    used_llm: bool = False


async def _coach_via_stream(req: TutorRequest, q: Question, prompt: str) -> _Coaching:
    """Stream the coaching to the learner's socket as the model writes it.

    Every delta is published as a ``tutor_token`` event, so a wait that used to
    be a spinner becomes visible text. The full reply is still parsed and
    returned, so the REST response, the cache and the audit event are exactly
    what the buffered path produces — the stream is an addition to the
    contract, never the source of truth.

    A stream that breaks *after* tokens were shown is the one case worth
    spelling out: the partial text is discarded and the deterministic offline
    fallback answers instead. Presenting half a walkthrough as the walkthrough
    would be the fabrication constitution §13 forbids; the client is told with
    an ``interrupted`` step so it can clear what it rendered.
    """
    await _emit(
        req,
        {
            "type": "tutor_step",
            "stage": "generating",
            "question_id": q.id,
            "streamed": True,
            "chain": list(llm.chain_names()),
        },
    )
    buffer: list[str] = []
    model_label = ""
    try:
        async for chunk in llm.astream(
            prompt,
            system=_section("system.streamed"),
            agent="lsat_tutor",
            prompt_id="lsat_tutor",
            prompt_version=PROMPT_VERSION,
            models=xai.interactive_overrides(),
        ):
            model_label = chunk.model_label
            buffer.append(chunk.text)
            await _emit(
                req,
                {
                    "type": "tutor_token",
                    "question_id": q.id,
                    "text": chunk.text,
                    "model": chunk.model_label,
                },
            )
    except llm.LLMStreamInterrupted as exc:
        logger.info("LSAT tutor stream interrupted: %s", exc)
        await _emit(
            req,
            {"type": "tutor_step", "stage": "interrupted", "question_id": q.id},
        )
        return _Coaching()
    except (
        TimeoutError,
        httpx.HTTPError,
        OSError,
        claude_code.ClaudeCodeUnavailableError,
        llm.LLMUnavailableError,
    ) as exc:
        logger.info("LSAT tutor falling back to offline path: %s", exc)
        return _Coaching()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LSAT tutor unexpected stream error: %s", exc, exc_info=True)
        return _Coaching()

    coaching, next_steps = _parse_stream_payload("".join(buffer))
    if not coaching:
        return _Coaching()
    await _emit(
        req,
        {
            "type": "tutor_step",
            "stage": "generated",
            "question_id": q.id,
            "model": model_label,
        },
    )
    return _Coaching(
        coaching=coaching,
        next_steps=next_steps,
        model=model_label or "unknown",
        confidence=0.85 if next_steps and len(coaching) > 80 else 0.7,
        used_llm=True,
    )


async def _coach_via_chain(req: TutorRequest, q: Question, prompt: str) -> _Coaching:
    """Ask the provider chain for coaching, degrading instead of raising.

    An empty :class:`_Coaching` is the signal to fall back offline: the caller
    must always be able to answer the learner, so every transport failure is
    swallowed here and recorded in the log (constitution §13 — an honest,
    source-grounded fallback beats a fabricated model answer).
    """
    await _emit(
        req,
        {
            "type": "tutor_step",
            "stage": "generating",
            "question_id": q.id,
            # The tier is not known until the chain picks one, so this event
            # says "a model call started", not which model. The `generated`
            # event that follows carries the label.
            "chain": list(llm.chain_names()),
        },
    )
    try:
        raw, model_label = await _generate_coaching(prompt)
        coaching, next_steps = _parse_llm_payload(raw)
    except (
        TimeoutError,
        httpx.HTTPError,
        OSError,
        claude_code.ClaudeCodeUnavailableError,
        llm.LLMUnavailableError,
    ) as exc:
        logger.info("LSAT tutor falling back to offline path: %s", exc)
        return _Coaching()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LSAT tutor unexpected error: %s", exc, exc_info=True)
        return _Coaching()

    if not coaching:
        return _Coaching()
    await _emit(
        req,
        {
            "type": "tutor_step",
            "stage": "generated",
            "question_id": q.id,
            "model": model_label,
        },
    )
    return _Coaching(
        coaching=coaching,
        next_steps=next_steps,
        model=model_label,
        # Heuristic confidence: longer, structured responses tend to be better.
        confidence=0.85 if next_steps and len(coaching) > 80 else 0.7,
        used_llm=True,
    )


def _current_trace_id() -> str | None:
    """The active OTEL trace, as the 32-hex id a viewer's URL takes.

    ``None`` when telemetry is off — ``init_tracing`` installs no SDK then, and
    the ambient span context is invalid rather than absent.
    """
    try:
        from opentelemetry import trace as otel_trace
    except Exception:  # pragma: no cover - optional dependency
        return None
    ctx = otel_trace.get_current_span().get_span_context()
    return f"{ctx.trace_id:032x}" if ctx.is_valid else None


async def tutor(req: TutorRequest, q: Question) -> TutorResponse:
    """Produce a tutor response for ``q``, under a span of its own.

    ``init_tracing`` instruments httpx and nothing else, so a DRF view has no
    ambient request span and the tutor's provider calls had no trace to belong
    to — which is why a walkthrough could not be linked to its trace the way an
    analysis can (BL-20260503-06). Opening the span here gives the chain's HTTP
    spans a parent and gives the response a deep link.

    The link is stamped on the way out rather than inside, so a cache hit
    carries *this* request's trace (or none at all) instead of the stale one
    that was stored with the walkthrough weeks ago.
    """
    try:
        from opentelemetry import trace as otel_trace
    except Exception:  # pragma: no cover - optional dependency
        return await _tutor(req, q)

    tracer = otel_trace.get_tracer("law_ai.lsat_tutor")
    with tracer.start_as_current_span("lsat_tutor.invoke") as span:
        span.set_attribute("lsat_tutor.question_id", q.id)
        span.set_attribute("lsat_tutor.prompt_version", PROMPT_VERSION)
        response = await _tutor(req, q)
        span.set_attribute("lsat_tutor.model", response.model)
        span.set_attribute("lsat_tutor.cached", response.cached)
        ctx = span.get_span_context()
        trace_id = f"{ctx.trace_id:032x}" if ctx.is_valid else None
    return response.model_copy(
        update={
            "trace_id": trace_id,
            "phoenix_trace_url": _phoenix_trace_url(trace_id),
        }
    )


async def _tutor(req: TutorRequest, q: Question) -> TutorResponse:
    """Produce a tutor response for ``q``, mixed with optional learner input.

    Always returns a populated response — falls back to an offline summary if
    the LLM is unreachable. Records an audit event regardless of path.
    """
    import time

    started = time.perf_counter()

    key, cached_response = _cache_lookup(req, q)
    if cached_response is not None:
        await _emit(
            req,
            {
                "type": "tutor_step",
                "stage": "cache_hit",
                "question_id": q.id,
                "model": cached_response.model,
            },
        )
        await _emit_complete(req, q, cached_response)
        _audit_event(req, q, cached_response)
        return cached_response

    passages = load_passages()
    concepts_by_id = load_concepts()
    passage = passages.get(q.passage_id) if q.passage_id else None
    concept_entries = [
        concepts_by_id[cid] for cid in q.concepts if cid in concepts_by_id
    ]

    streaming = bool(req.stream_tokens and req.stream_id)
    prompt = _build_prompt(
        _PromptCtx(q, passage, concept_entries),
        req.user_choice,
        req.user_question,
        streamed=streaming,
        trace=req.trace,
    )

    attempt = await (
        _coach_via_stream(req, q, prompt)
        if streaming
        else _coach_via_chain(req, q, prompt)
    )
    used_llm = attempt.used_llm
    coaching, next_steps = attempt.coaching, attempt.next_steps
    model_used, confidence = attempt.model, attempt.confidence

    if not coaching:
        await _emit(
            req,
            {
                "type": "tutor_step",
                "stage": "fallback",
                "question_id": q.id,
                "model": model_used,
            },
        )
        coaching, next_steps = _fallback_coaching(
            q, req.user_choice, req.user_question, concept_entries, req.trace
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

    # Persist LLM-produced walkthroughs so the next identical request is a
    # cache hit; offline fallbacks are deterministic and cheap, so they are
    # never cached (a later request should retry the chain).
    if used_llm:
        try:
            llm_cache.put(key, response.model_dump())
        except Exception:  # pragma: no cover - cache failure must not block UX
            logger.warning("llm_cache.put failed for lsat_tutor", exc_info=True)

    await _emit_complete(req, q, response)
    _audit_event(req, q, response)
    return response


async def _emit_complete(req: TutorRequest, q: Question, resp: TutorResponse) -> None:
    """Terminal stream event, mirroring the analysis path's ``complete``."""
    await _emit(
        req,
        {
            "type": "complete",
            "question_id": q.id,
            "model": resp.model,
            "used_llm": resp.used_llm,
            "cached": resp.cached,
            "confidence": resp.confidence,
            "requires_human_review": resp.requires_human_review,
        },
    )


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
        "cached": resp.cached,
        # Read off the ambient span rather than the response: the response is
        # stamped with the trace on the way out, after this runs.
        "trace_id": _current_trace_id(),
    }
    audit_store.record(event)
