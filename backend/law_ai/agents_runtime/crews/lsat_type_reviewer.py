"""LSATTypeReviewer — a model's blind read of a question's type (spec 054).

Spec 053 stamped every bank item with the archetype its stem cues identify,
and the diagnosis exercise marks learners against that stamp. The stamp is a
rule's output, and a rule can be wrong in a way no rule-based test catches:
a stem whose phrasing matches one cue while the argument does the work of
another type. This crew asks a model to read the item the way an instructor
would — question sentence first, stimulus to break ties — and name the type
from the section's menu, **without** seeing the stamp. Disagreement is a
report for a human (``lsat_type_review_sweep`` files it as a ``typecheck``
proposal); approving that report restamps the item, rejecting it keeps the
stamp. Nothing here writes to the bank.

Same contract as the other crews: the provider chain via ``law_ai.core.llm``,
one ``provenance.log_agent_call`` per run, a degraded result — never an
exception — when no provider answers, and a response cache keyed on the
prompt version so a sweep can resume without re-billing.
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
from law_ai.lsat.factory.taxonomy import archetypes_for
from law_ai.lsat.services import llm_cache
from law_ai.lsat.services.bank import Question, load_bank, load_passages
from law_ai.lsat.services.playbooks import classify, load_playbooks

logger = logging.getLogger("law_ai.agents.lsat_type_reviewer")

PROMPT_VERSION = "lsat_type_reviewer/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_type_reviewer.v1.md"
)
CACHE_KIND = "typecheck"
_MAX_PASSAGE_CHARS = 4000

_LLM_SYSTEM = (
    "You are an experienced LSAT instructor naming a question's type from a "
    "menu. Respond with a single JSON object only — no preamble and no markdown "
    "code fences."
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "archetype_id": {"type": "string"},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["archetype_id", "rationale", "confidence"],
    "additionalProperties": False,
}


class TypeReviewInput(BaseModel):
    question_id: str
    refresh: bool = False


class TypeReview(BaseModel):
    """One blind type read against the stamp."""

    question_id: str
    section: str
    stamped_archetype: str | None
    #: What the deterministic classifier says from the stem alone.
    cue_archetype: str | None
    model_archetype: str | None = None
    #: ``model_archetype == stamped_archetype``; None without a model read.
    agrees: bool | None = None
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = "fallback/offline"
    used_llm: bool = False
    cached: bool = False
    degraded: bool = False
    latency_ms: float = 0.0
    prompt_version: str = PROMPT_VERSION


class TypeReviewOutput(BaseModel):
    review: TypeReview
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_payload(q: Question) -> dict[str, Any]:
    """The item without its stamp, plus the section's type menu.

    >>> build_payload(load_bank()["lr-002"])["menu"][0]["archetype_id"].startswith("lr-")
    True
    """
    books = load_playbooks()
    payload: dict[str, Any] = {
        "item": {
            "section": q.section,
            "stem": q.stem,
            "choices": [c.model_dump() for c in q.choices],
        },
        "menu": [
            {
                "archetype_id": a.id,
                "name": a.name,
                "task": books[a.id].task if a.id in books else None,
            }
            for a in archetypes_for(q.section)
        ],
    }
    passage = load_passages().get(q.passage_id) if q.passage_id else None
    if passage is not None:
        payload["passage"] = {
            "title": passage.title,
            "passage": (passage.passage or "")[:_MAX_PASSAGE_CHARS],
            "setup": (passage.setup or "")[:_MAX_PASSAGE_CHARS],
            "rules": list(passage.rules),
        }
    return payload


def _parse(raw: str, *, menu: set[str]) -> tuple[str | None, str, float]:
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"type reviewer response not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("type reviewer response is not an object")
    pick = str(obj.get("archetype_id") or "").strip()
    if pick not in menu:
        raise ValueError(f"type reviewer picked {pick!r}, not on the menu")
    rationale = str(obj.get("rationale") or "").strip()[:800]
    try:
        confidence = min(1.0, max(0.0, float(obj.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    return pick, rationale, confidence


async def review_type(q: Question, *, refresh: bool = False) -> TypeReview:
    """Blind-read ``q``'s type and compare it with the stamp (cached per prompt version)."""
    started = time.perf_counter()
    cue = classify(q.model_copy(update={"archetype": None})).archetype_id
    key = llm_cache.cache_key(
        CACHE_KIND, {"question_id": q.id, "prompt_version": PROMPT_VERSION}
    )
    if not refresh:
        hit = llm_cache.get(key)
        if hit is not None:
            try:
                return TypeReview.model_validate(
                    {
                        **hit,
                        "stamped_archetype": q.archetype,
                        "cue_archetype": cue,
                        "agrees": hit.get("model_archetype") == q.archetype,
                        "cached": True,
                        "latency_ms": 0.0,
                    }
                )
            except Exception:  # malformed row (old schema) — re-read
                pass

    review = TypeReview(
        question_id=q.id,
        section=q.section,
        stamped_archetype=q.archetype,
        cue_archetype=cue,
    )
    menu = {a.id for a in archetypes_for(q.section)}
    prompt = (
        _load_prompt_template()
        + "\n\n## Item\n\n```json\n"
        + json.dumps(build_payload(q), indent=2, ensure_ascii=False)
        + "\n```\n"
    )
    try:
        result = await llm.agenerate(
            prompt,
            system=_LLM_SYSTEM,
            response_schema=_RESPONSE_SCHEMA,
            agent="lsat_type_reviewer",
        )
        pick, rationale, confidence = _parse(result.text, menu=menu)
        review = review.model_copy(
            update={
                "model_archetype": pick,
                "agrees": pick == q.archetype,
                "rationale": rationale,
                "confidence": confidence,
                "model": result.model_label,
                "used_llm": True,
            }
        )
    except (
        TimeoutError,
        httpx.HTTPError,
        OSError,
        ValueError,
        claude_code.ClaudeCodeUnavailableError,
        llm.LLMUnavailableError,
    ) as exc:
        logger.info("LSATTypeReviewer degraded: %s", exc)
        review = review.model_copy(
            update={"degraded": True, "rationale": f"[OFFLINE] {str(exc)[:200]}"}
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LSATTypeReviewer unexpected error: %s", exc, exc_info=True)
        review = review.model_copy(update={"degraded": True})
    review = review.model_copy(
        update={"latency_ms": round((time.perf_counter() - started) * 1000.0, 2)}
    )
    if review.used_llm:
        llm_cache.put(
            key,
            {
                "question_id": q.id,
                "section": q.section,
                "model_archetype": review.model_archetype,
                "rationale": review.rationale,
                "confidence": review.confidence,
                "model": review.model,
                "used_llm": True,
                "prompt_version": PROMPT_VERSION,
            },
        )
    return review


class LSATTypeReviewer:
    """Names a bank question's type blind and reports disagreement (spec 054)."""

    name = "LSATTypeReviewer"
    description = (
        "Reads one bank question without its type stamp and names the archetype "
        "from the section's menu. A disagreement with the stamp is a report for "
        "a human; the crew never restamps anything itself."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> TypeReviewOutput:
        inp = TypeReviewInput.model_validate(input_data)
        q = load_bank()[inp.question_id]
        review = await review_type(q, refresh=inp.refresh)
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "question_id": q.id,
                "section": q.section,
                "refresh": inp.refresh,
            },
            output_data={
                "stamped_archetype": review.stamped_archetype,
                "model_archetype": review.model_archetype,
                "agrees": review.agrees,
                "degraded": review.degraded,
                "cached": review.cached,
            },
            model=review.model,
            latency_ms=review.latency_ms,
            confidence=review.confidence,
            sources=[{"question_id": q.id}],
        )
        return TypeReviewOutput(review=review, trace_id=trace_id)
