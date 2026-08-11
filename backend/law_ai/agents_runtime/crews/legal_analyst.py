"""
Legal Analyst Agent

Produces structured IRAC briefs, issue spotting, argument mapping,
and risk assessment using GraphRAG retrieval + LLM reasoning.

Spec 010 FR-3 / T-006, promoted to the DEFAULT engine by spec 027: when
``input_data["use_langgraph"]`` is truthy (the ``AnalysisRequest`` default),
delegate to :class:`law_ai.agents_runtime.graphs.LegalWorkflow` so the
response is backed by a real Ollama call + provenance trace. The path is
wrapped in a resilience boundary: if Ollama is unreachable or the LangGraph
stack is missing, it returns an honestly-degraded refusal instead of raising.

Dev-time Claude Code path: when the shared :func:`law_ai.core.claude_code.is_active`
gate is on (``LSAT_LLM_PROVIDER=claude_code`` + token, development only), the
default (non-LangGraph) path produces a real IRAC analysis via Claude Code over
OAuth — the same dev-only provider the LSAT agents use. It degrades to an
offline placeholder if Claude Code is unreachable, so the Analysis Studio never
hard-fails. Outside that gate the default path returns an honestly-degraded
refusal (``degraded=True``, confidence 0.0, forced human review) — it must
never fabricate analysis or log it under a real model name (constitution §4/§13).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code
from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.agents.legal_analyst")


class IRACOutput(BaseModel):
    issue: str = Field(..., description="Key legal issue identified")
    rule: str = Field(..., description="Applicable legal rules / black letter law")
    application: str = Field(..., description="Application of rules to facts")
    conclusion: str = Field(..., description="Conclusion and recommended action")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    degraded: bool = Field(
        default=False,
        description=(
            "True when no real analysis ran (unimplemented/offline path). "
            "Degraded output must be excluded from confidence aggregation "
            "and always forces human review."
        ),
    )
    requires_review: bool = Field(
        default=False,
        description=(
            "Structured HITL flag: True when this output must be reviewed "
            "by a human (unverified citations, refusal, or degraded path)."
        ),
    )
    retrieval: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Retrieval coverage envelope (queries, result_count, "
            "jurisdiction_requested, coverage_note) when a retrieval-backed "
            "path ran — constitution §13 'absence is reported'."
        ),
    )
    reasoning_trace: list[str] = Field(default_factory=list)
    trace_id: str | None = Field(
        default=None, description="Provenance trace_id from log_agent_call"
    )
    phoenix_trace_url: str | None = Field(
        default=None,
        description="Deep-link to the Phoenix span tree (spec 010 FR-3).",
    )
    langgraph_thread_id: str | None = Field(
        default=None,
        description="LangGraph checkpoint thread id; resume with the same id.",
    )


# ---------------------------------------------------------------------------
# Claude Code IRAC path (dev-time only) — shared gate with the LSAT agents.
# ---------------------------------------------------------------------------

_IRAC_SYSTEM = (
    "You are a careful legal analyst. Produce a rigorous IRAC analysis (Issue, "
    "Rule, Application, Conclusion). Be precise and cite authorities only by name "
    "when you are confident — never invent case citations or URLs. Respond with a "
    "single JSON object only, no preamble and no markdown code fences."
)

# Structured-output schema: forces schema-valid JSON. ``key_authorities`` lists
# case/statute names only (no fabricated URLs); confidence is clamped on parse.
_IRAC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issue": {"type": "string"},
        "rule": {"type": "string"},
        "application": {"type": "string"},
        "conclusion": {"type": "string"},
        "key_authorities": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "issue",
        "rule",
        "application",
        "conclusion",
        "key_authorities",
        "confidence",
    ],
    "additionalProperties": False,
}


def _build_irac_prompt(question: str, *, facts: str, jurisdiction: str) -> str:
    parts = [
        "Analyze the following legal question using the IRAC method.",
        f"Jurisdiction: {jurisdiction}" if jurisdiction else "",
        f"Question: {question}" if question else "Question: (none provided)",
        f"Facts: {facts}" if facts else "",
        "Identify the controlling legal issue, state the applicable rule / "
        "black-letter law, apply it to the facts, and give a conclusion with a "
        "recommended action. List the case names or statutes your analysis relies "
        "on in 'key_authorities' (names only; omit any you are unsure of). Provide "
        "a confidence between 0 and 1.",
    ]
    return "\n\n".join(p for p in parts if p)


def _clamp_confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _irac_from_payload(data: Any, question: str) -> IRACOutput:
    if not isinstance(data, dict):
        raise ValueError("IRAC response was not a JSON object")
    authorities = data.get("key_authorities") or []
    return IRACOutput(
        issue=str(data.get("issue") or question[:200] or "(no issue identified)"),
        rule=str(data.get("rule") or ""),
        application=str(data.get("application") or ""),
        conclusion=str(data.get("conclusion") or ""),
        sources=[
            {"title": str(a), "verified": False} for a in authorities if str(a).strip()
        ][:10],
        confidence=_clamp_confidence(data.get("confidence")),
        # Model-named authorities are ungrounded until resolved against the
        # knowledge graph — a human must review before relying on them.
        requires_review=True,
        reasoning_trace=[
            "Model-generated IRAC via Claude Code (dev-time).",
            "Authorities are unverified — human review / GraphRAG grounding required.",
        ],
    )


def _fallback_irac(question: str) -> IRACOutput:
    return IRACOutput(
        issue=question[:200] or "(no question provided)",
        rule="[OFFLINE FALLBACK] The dev LLM was unreachable — no analysis generated.",
        application=(
            "Claude Code was unreachable (e.g. a transient overload). Retry, or "
            "run with Ollama / the LangGraph workflow."
        ),
        conclusion=(
            "Degraded: no LLM analysis produced. This row exists for auditability "
            "and must not be relied upon."
        ),
        sources=[],
        confidence=0.0,
        degraded=True,
        requires_review=True,
        reasoning_trace=["offline fallback — LLM unreachable"],
    )


def _langgraph_fallback_irac(question: str, reason: str) -> IRACOutput:
    """Honest degraded output when the LangGraph/Ollama engine is unavailable."""
    return IRACOutput(
        issue=question[:200] or "(no question provided)",
        rule=(
            "[ENGINE UNAVAILABLE] The LangGraph/Ollama analysis engine could "
            f"not run: {reason}"
        ),
        application=(
            "No analysis was performed. Start the Ollama service "
            "(`make local-ai-up`) and retry."
        ),
        conclusion=(
            "Degraded: no legal analysis produced. This output exists for "
            "auditability and must not be relied upon."
        ),
        sources=[],
        confidence=0.0,
        degraded=True,
        requires_review=True,
        reasoning_trace=[f"langgraph engine unavailable — {reason}"],
    )


class LegalAnalyst:
    name = "LegalAnalyst"
    description = "Produces high-quality IRAC legal analysis with source grounding"

    async def run(self, input_data: dict[str, Any]) -> IRACOutput:
        # Spec 027: LangGraph is the DEFAULT engine (AnalysisRequest defaults
        # use_langgraph=true). The explicit-false escape hatch keeps the
        # dev-time Claude Code path and the honest degraded stub reachable.
        if input_data.get("use_langgraph"):
            return await self._run_via_langgraph(input_data)
        if claude_code.is_active():
            return await self._run_via_claude_code(input_data)
        return await self._run_legacy(input_data)

    async def _run_via_claude_code(self, input_data: dict[str, Any]) -> IRACOutput:
        """Dev-time path: real IRAC analysis via Claude Code over OAuth.

        Pinned with structured outputs so the response is schema-valid JSON, and
        degrades to a clearly-labeled offline placeholder on any provider failure
        (e.g. a transient overload) — never raising into the caller.
        """
        start = time.time()
        question = input_data.get("text") or input_data.get("question") or ""
        prompt = _build_irac_prompt(
            question,
            facts=str(input_data.get("facts") or ""),
            jurisdiction=str(input_data.get("jurisdiction") or ""),
        )
        try:
            raw = await claude_code.generate(
                prompt, system=_IRAC_SYSTEM, response_schema=_IRAC_SCHEMA
            )
            output = _irac_from_payload(claude_code.loads_first_json(raw), question)
            model_used = claude_code.model_label()
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
        ) as exc:
            logger.info("LegalAnalyst falling back to offline IRAC: %s", exc)
            output = _fallback_irac(question)
            model_used = "fallback/offline"

        latency = (time.time() - start) * 1000
        output.trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data=input_data,
            output_data=output.model_dump(),
            model=model_used,
            latency_ms=latency,
            confidence=output.confidence,
            sources=output.sources,
        )
        return output

    async def _run_legacy(self, input_data: dict[str, Any]) -> IRACOutput:
        """Non-LangGraph, non-Claude path: honestly unimplemented.

        This path used to return a hardcoded negligence IRAC at confidence
        0.82 logged under a real model name — fabricated legal content that
        cleared the HITL threshold. Per constitution §4/§13 it now returns a
        clearly-degraded refusal at confidence 0.0 that always requires
        human review. Use ``use_langgraph=true`` for a real Ollama-backed run.
        """
        start = time.time()
        question = str(
            input_data.get("text") or input_data.get("question") or ""
        ).strip()

        output = IRACOutput(
            issue=question[:200] or "(no question provided)",
            rule=(
                "[NOT IMPLEMENTED] The default analysis path performs no "
                "retrieval and no LLM reasoning — no rule can be stated."
            ),
            application=(
                "No analysis was performed. Re-run with use_langgraph=true "
                "for the retrieval-backed Ollama workflow."
            ),
            conclusion=(
                "Degraded: no legal analysis produced. This output exists "
                "for auditability and must not be relied upon."
            ),
            sources=[],
            confidence=0.0,
            degraded=True,
            requires_review=True,
            reasoning_trace=[
                "default path — no retrieval performed, no LLM invoked",
            ],
        )

        latency = (time.time() - start) * 1000
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data=input_data,
            output_data=output.model_dump(),
            model="degraded/not-implemented",
            latency_ms=latency,
            confidence=output.confidence,
            sources=output.sources,
        )
        output.trace_id = trace_id
        return output

    async def _run_via_langgraph(self, input_data: dict[str, Any]) -> IRACOutput:
        """Spec 010 T-006: delegate to LegalWorkflow.

        We map the workflow's free-form ``answer`` into the IRAC fields by
        copying the answer text into ``application`` and surfacing the
        confidence + citations + Phoenix trace url. The richer
        issue/rule/conclusion split lands in BL-20260502-04 (LegalAnalyst
        backfill onto LegalWorkflow).
        """
        from law_ai.agents_runtime import llm as llm_runtime

        question = input_data.get("text") or input_data.get("question") or ""

        # Resilience boundary (spec 027): as the DEFAULT engine this path must
        # never 500 the API. Probe first (milliseconds, TTL-cached) so a down
        # Ollama degrades honestly instead of burning the retry budget.
        if not await llm_runtime.ollama_available_async():
            output = _langgraph_fallback_irac(
                str(question), "Ollama unreachable (availability probe failed)"
            )
            output.trace_id = provenance.log_agent_call(
                agent_name=self.name,
                input_data=input_data,
                output_data=output.model_dump(),
                model="fallback/offline",
                latency_ms=0.0,
                confidence=0.0,
            )
            return output

        try:
            from law_ai.agents_runtime.graphs import LegalWorkflow

            workflow = LegalWorkflow()
            result = await workflow.invoke(
                question,
                jurisdiction=input_data.get("jurisdiction"),
                case_id=input_data.get("case_id"),
            )
        except Exception as exc:
            # Deliberately broad: this is the resilience boundary for the
            # DEFAULT analysis engine, so it must never surface a 500. The
            # failure modes are open-ended (missing langgraph extra, Ollama
            # transport errors, a model that isn't pulled yet → the client
            # library's own ResponseError, Neo4j faults, LangGraph internals),
            # and every one of them degrades to the same honest refusal that
            # is logged and flagged for human review.
            logger.warning(
                "LegalAnalyst langgraph engine failed: %s", exc, exc_info=True
            )
            output = _langgraph_fallback_irac(
                str(question), f"{type(exc).__name__}: {str(exc)[:200]}"
            )
            output.trace_id = provenance.log_agent_call(
                agent_name=self.name,
                input_data=input_data,
                output_data=output.model_dump(),
                model="fallback/offline",
                latency_ms=0.0,
                confidence=0.0,
            )
            return output

        # Keep EVERY citation — the unverified (hallucination-flagged) ones
        # are exactly what a reviewer must inspect; stripping them hides the
        # problem the cite-check exists to surface.
        sources = [
            {
                "title": c.text[:120],
                "url": c.source_url or "",
                "verified": c.resolved_case_id is not None,
                "resolved_case_id": c.resolved_case_id,
            }
            for c in result.citations
        ]
        verified_count = sum(1 for c in result.citations if c.resolved_case_id)
        unverified_count = len(result.citations) - verified_count
        if result.retrieval_stats.result_count == 0:
            conclusion = (
                "No sources were retrieved from the knowledge graph — the "
                "workflow refused to answer. Absence of results in this "
                "corpus does NOT mean no such law exists."
            )
        elif not result.citations:
            # Retrieval succeeded but the model cited nothing — §13
            # attribution is unmet, so this must not read as "complete".
            conclusion = (
                "Pending human review — the answer cites no authorities "
                "(every legal proposition must name its issuing authority)."
            )
        elif unverified_count:
            conclusion = (
                f"Pending human review — {unverified_count} of "
                f"{len(result.citations)} citation(s) could not be resolved "
                "against the knowledge graph."
            )
        else:
            conclusion = (
                f"Analysis complete; {verified_count} citation(s) resolved "
                "against the knowledge graph."
            )
        output = IRACOutput(
            issue=question[:200] or "(no question provided)",
            rule="See cited authorities below.",
            application=result.answer,
            conclusion=conclusion,
            sources=sources,
            confidence=result.confidence,
            requires_review=result.human_approval_required,
            retrieval=result.retrieval_stats.model_dump(),
            reasoning_trace=[
                f"LangGraph thread {result.langgraph_thread_id}",
                f"latency {result.latency_ms} ms",
                f"retrieval: {result.retrieval_stats.result_count} passage(s) "
                f"for queries {result.retrieval_stats.queries!r}",
            ],
            trace_id=result.trace_id,
            phoenix_trace_url=result.phoenix_trace_url,
            langgraph_thread_id=result.langgraph_thread_id,
        )
        provenance.log_agent_call(
            agent_name=self.name,
            input_data=input_data,
            output_data=output.model_dump(),
            model=f"langgraph::{result.langgraph_thread_id}",
            latency_ms=result.latency_ms,
            confidence=result.confidence,
            sources=sources,
        )
        return output
