"""
Legal Analyst Agent

Produces structured IRAC briefs, issue spotting, argument mapping,
and risk assessment using GraphRAG retrieval + LLM reasoning.

Spec 010 FR-3 / T-006, promoted to the DEFAULT engine by spec 027: when
``input_data["use_langgraph"]`` is truthy (the ``AnalysisRequest`` default),
delegate to :class:`law_ai.agents_runtime.graphs.LegalWorkflow` so the
response is backed by a real retrieval-grounded model call + provenance trace.
That path is wrapped in a resilience boundary: if the engine is unavailable it
returns an honestly-degraded refusal instead of raising.

Spec 034: both paths run on the shared provider chain in
:mod:`law_ai.core.llm` — Claude over OAuth, then Claude over the Anthropic API
key, then local Ollama. The explicit ``use_langgraph=false`` escape hatch calls
the chain directly (structured outputs pin schema-valid JSON) without the
graph's retrieval nodes. When every provider fails, the analyst degrades to a
clearly-labeled offline placeholder — it must never fabricate analysis or log
it under a real model name (constitution §4/§13).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, model_validator

from law_ai.agents_runtime.attribution import (
    Attribution,
    attribution_from_passage,
    check_attribution,
)
from law_ai.core import claude_code, llm, xai
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
    degraded_reason: Literal["engine_unavailable", "offline_fallback"] | None = Field(
        default=None,
        description=(
            "Which degraded path produced this row (BL-20260810-16). "
            "`engine_unavailable`: the LangGraph engine could not start, so "
            "the advice is to start a provider (Ollama when the chain is "
            "pinned local). `offline_fallback`: every tier in "
            "LLM_PROVIDER_CHAIN failed. The UI needs the difference: only one "
            "of them is fixed by `make local-ai-up`. The `[ENGINE "
            "UNAVAILABLE]` / `[OFFLINE FALLBACK]` prefixes in `rule` stay as "
            "the signal for payloads written before this field existed."
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
        description=(
            "DEPRECATED alias of `trace_url`, kept for clients that already "
            "read it (BL-20260906-10). Always equal to `trace_url`."
        ),
    )
    trace_url: str | None = Field(
        default=None,
        description=(
            "Deep-link to this run's span tree (spec 010 FR-3). Named for the "
            "backend-agnostic `core.telemetry.trace_url`, since the collector "
            "is no longer necessarily Phoenix."
        ),
    )
    langgraph_thread_id: str | None = Field(
        default=None,
        description="LangGraph checkpoint thread id; resume with the same id.",
    )
    resumed: bool = Field(
        default=False,
        description=(
            "True when the requested `thread_id` already had persisted state "
            "before this run — i.e. the run resumed a thread rather than "
            "starting one (BL-20260810-13)."
        ),
    )

    @model_validator(mode="after")
    def _mirror_trace_url(self) -> IRACOutput:
        """Emit both spellings from whichever one the caller set.

        The deprecation window (BL-20260906-10) is only safe if the two can
        never disagree, so it is enforced here rather than at each of the
        construction sites — one of which is the checkpoint replay path, where
        a stored payload may carry only the old name.
        """
        if self.trace_url is None:
            self.trace_url = self.phoenix_trace_url
        elif self.phoenix_trace_url is None:
            self.phoenix_trace_url = self.trace_url
        return self


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
            "Model-generated IRAC via the provider chain.",
            # Overwritten by LegalAnalyst._ground_authorities once the graph
            # has had its say (BL-20260615-03); this is the pre-grounding state.
            "Authorities are unverified — GraphRAG grounding pending.",
        ],
    )


def _fallback_irac(question: str) -> IRACOutput:
    return IRACOutput(
        issue=question[:200] or "(no question provided)",
        rule=(
            "[OFFLINE FALLBACK] No LLM provider was reachable — no analysis generated."
        ),
        application=(
            "Every provider in LLM_PROVIDER_CHAIN failed (Claude OAuth, the "
            "Anthropic API key, then local Ollama). Check credentials and "
            "connectivity, then retry."
        ),
        conclusion=(
            "Degraded: no LLM analysis produced. This row exists for auditability "
            "and must not be relied upon."
        ),
        sources=[],
        confidence=0.0,
        degraded=True,
        degraded_reason="offline_fallback",
        requires_review=True,
        reasoning_trace=["offline fallback — LLM unreachable"],
    )


async def _engine_ready() -> tuple[bool, str]:
    """Chain-aware readiness gate for the LangGraph engine (BL-20260615-02).

    The old gate probed Ollama unconditionally, so a Claude-only deployment
    (``LLM_PROVIDER_CHAIN=claude_code`` or simply Ollama not running) was
    refused before ``LegalWorkflow`` was ever constructed — even though the
    workflow is ``ChatProviderChain``-backed and would have been served by
    Claude. Now the probe only runs when Ollama is the *only* configured tier,
    which is the one case where a cheap local reachability check is both
    meaningful and free.

    Returns ``(ready, reason)``; ``reason`` is empty when ready.
    """
    from law_ai.core import llm as core_llm

    try:
        configured = [p for p in core_llm.build_chain() if p.configured()]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("chain readiness check failed: %s", exc)
        return True, ""  # let the workflow's own error path speak

    if not configured:
        return False, "no provider in LLM_PROVIDER_CHAIN is configured"

    if all(p.name == "ollama" for p in configured):
        from law_ai.agents_runtime import llm as llm_runtime

        if not await llm_runtime.ollama_available_async():
            return False, (
                "Ollama is the only configured provider and is unreachable "
                "(availability probe failed)"
            )
    return True, ""


def _coerce_matter_id(raw: Any) -> int | None:
    """``matter_id`` as an int, or ``None`` for anything unusable.

    The payload is a plain dict assembled by whichever caller ran the analyst,
    so a string id or a stray empty value must degrade to "no matter" rather
    than raising inside the resilience boundary.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _langgraph_fallback_irac(question: str, reason: str) -> IRACOutput:
    """Honest degraded output when the LangGraph engine cannot run."""
    return IRACOutput(
        issue=question[:200] or "(no question provided)",
        rule=(
            "[ENGINE UNAVAILABLE] The LangGraph analysis engine could "
            f"not run: {reason}"
        ),
        application=(
            "No analysis was performed. Configure a provider in "
            "`LLM_PROVIDER_CHAIN` (`claude setup-token`, `ANTHROPIC_API_KEY`, "
            "`make xai-login`) or start Ollama (`make local-ai-up`), then retry."
        ),
        conclusion=(
            "Degraded: no legal analysis produced. This output exists for "
            "auditability and must not be relied upon."
        ),
        sources=[],
        confidence=0.0,
        degraded=True,
        degraded_reason="engine_unavailable",
        requires_review=True,
        reasoning_trace=[f"langgraph engine unavailable — {reason}"],
    )


# ---------------------------------------------------------------------------
# Authority grounding (BL-20260615-03)
# ---------------------------------------------------------------------------


class DeltaSink(Protocol):
    """Where streamed IRAC deltas go while the model is writing.

    Two optional halves — the text, and the tier that produced it — so the
    same sink satisfies :data:`law_ai.agents_runtime.graphs.legal_workflow.DeltaSink`
    (which passes text alone) and the direct-LLM path (which knows the model
    from the first chunk).
    """

    async def __call__(
        self, text: str, model: str | None = None
    ) -> None:  # pragma: no cover - structural
        ...


CiteResolver = Callable[[list[str]], Awaitable[dict[str, str | None]]]


async def _default_cite_resolver(names: list[str]) -> dict[str, str | None]:
    """Resolve model-named authorities against the citation graph."""
    from law_ai.core.neo4j.citation_resolver import resolve_with_default_driver

    return await resolve_with_default_driver(names)


async def _name_lookup(
    names: list[str], retriever: Any
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Fulltext lookup of the authorities the model named, by case name.

    ``resolve_citations`` matches ``Case.aliases`` — normalized reporter
    citations — while the IRAC prompt asks for *case names*, so the alias leg
    misses almost everything on its own. One lexical GraphRAG query per name
    closes that gap: a passage whose title matches the model's name grounds it
    in a real ``:Case`` node. Never invents a match; a miss stays a miss.

    Returns the matched ``(case_id, passage)`` per name: the passage carries
    the court and decision date the §13 attribution is built from
    (BL-20260803-04), which is why every named authority is looked up now, not
    only the ones the alias resolver missed.
    """
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    for name in names:
        try:
            passages = await retriever({"question": name, "queries": [name]})
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("authority name lookup failed for %r: %s", name, exc)
            return found
        wanted = name.casefold().strip()
        for passage in passages:
            title = str(passage.get("title") or "").casefold()
            case_id = str(passage.get("id") or "").strip()
            if not case_id or not title:
                continue
            if wanted in title or title in wanted:
                found[name] = (case_id, dict(passage))
                break
    return found


@asynccontextmanager
async def _analysis_checkpointer() -> AsyncIterator[Any]:
    """Yield a saver for one analysis request, or ``None`` (BL-20260810-13).

    Per-request rather than pooled: ``/api/analysis`` runs under
    ``async_to_sync`` on daphne *and* inside Celery workers, and a saver bound
    to the wrong event loop is worse than no saver at all. The cost is one
    Postgres connection for the life of a request, which the existing ``llm``
    throttle scope already bounds.

    A checkpointer that will not open degrades to an unpersisted run — losing
    resumability is not a reason to fail an analysis.
    """
    from law_ai.agents_runtime.graphs.runtime import build_checkpointer

    try:
        maybe = build_checkpointer()
    except Exception as exc:
        logger.warning("analysis checkpointer unavailable: %s", exc)
        yield None
        return

    if not isinstance(maybe, AbstractAsyncContextManager):
        yield maybe
        return

    # Only the *open* is guarded. Wrapping the yield in a try/except would
    # swallow whatever the caller raised and then yield a second time, which
    # is an error in an async generator ("generator didn't stop after
    # athrow()") and would mask the real failure from the resilience boundary.
    async with AsyncExitStack() as stack:
        try:
            saver: Any = await stack.enter_async_context(maybe)
        except Exception as exc:
            logger.warning("analysis checkpointer failed to open: %s", exc)
            saver = None
        yield saver


class ThreadDivergence(Exception):
    """A resume request that contradicts the thread it names (BL-20260905-81).

    Resuming ``thread_id`` with a different question or jurisdiction used to
    overwrite the checkpointed channels silently, so the thread's own record
    of what was asked changed under it and the earlier run became
    unreproducible. A divergent resume is a caller mistake, not an engine
    failure: ``/api/analysis`` refuses it with 409 and the caller either
    restates the original question or omits ``thread_id`` to branch a fresh
    thread.
    """

    def __init__(
        self, thread_id: str, field: str, checkpointed: str, requested: str
    ) -> None:
        self.thread_id = thread_id
        self.field = field
        self.checkpointed = checkpointed
        self.requested = requested
        super().__init__(
            f"thread {thread_id!r} was checkpointed with a different {field} "
            f"({checkpointed[:200]!r}, not {requested[:200]!r}); restate it or "
            "omit thread_id to start a new thread"
        )


async def _thread_state_values(workflow: Any, thread_id: str) -> dict[str, Any]:
    """The checkpointed channel values for ``thread_id`` (``{}`` when fresh).

    Probed *before* the run so ``resumed`` describes what the caller asked
    for, not what this run just wrote, and so the continuity check below sees
    the *previous* question rather than the one about to be written. A probe
    failure reports "fresh" rather than raising — an unknown resume status
    must not fail the analysis.
    """
    try:
        snapshot = await workflow.get_state(thread_id)
    except Exception as exc:
        logger.info("thread state probe failed for %s: %s", thread_id, exc)
        return {}
    values = getattr(snapshot, "values", None)
    return dict(values) if isinstance(values, dict) else {}


def _check_thread_continuity(
    thread_id: str,
    values: dict[str, Any],
    *,
    question: str,
    jurisdiction: str | None,
) -> None:
    """Raise :class:`ThreadDivergence` when a resume changes the ask.

    Only the two channels that define *what was asked* are pinned. Everything
    a run legitimately recomputes (retrieved passages, citations, the answer)
    is free to change — that is the point of resuming.
    """
    prior_question = str(values.get("question") or "")
    if prior_question and prior_question != question:
        raise ThreadDivergence(thread_id, "question", prior_question, question)
    prior_jurisdiction = values.get("jurisdiction") or None
    if prior_jurisdiction != (jurisdiction or None):
        raise ThreadDivergence(
            thread_id,
            "jurisdiction",
            str(prior_jurisdiction),
            str(jurisdiction),
        )


class LegalAnalyst:
    name = "LegalAnalyst"
    description = "Produces high-quality IRAC legal analysis with source grounding"

    def __init__(
        self,
        *,
        cite_resolver: CiteResolver | None = None,
        name_retriever: Any = None,
    ) -> None:
        """:param cite_resolver: ``names -> {name: case_id | None}``. Defaults to
        the shared Neo4j alias resolver.
        :param name_retriever: GraphRAG retriever used as the case-name
        fallback. ``None`` (the default) builds the shared one lazily; pass a
        fake in tests so no Neo4j is required.
        """
        self._cite_resolver = cite_resolver or _default_cite_resolver
        self._name_retriever = name_retriever

    def _get_name_retriever(self) -> Any:
        if self._name_retriever is None:
            from law_ai.agents_runtime.tools.graph_rag import build_default_retriever

            self._name_retriever = build_default_retriever()
        return self._name_retriever

    async def _ground_authorities(
        self, output: IRACOutput, jurisdiction: str | None = None
    ) -> None:
        """Resolve and attribute model-named authorities, in place.

        Constitution §1 source-grounding: the direct-LLM path must not present
        model-generated case names as authorities. Each name is resolved to a
        real ``:Case`` id (alias resolver first, then a lexical name lookup);
        anything that does not resolve is marked ``verified: False`` and keeps
        the output pinned for human review. A graph fault degrades to "resolver
        unavailable" and never raises.

        §13 attribution rides on the same lookup (BL-20260803-04): the matched
        passage supplies court, jurisdiction, decision date and
        binding/persuasive, so every emitted proposition names its issuing
        authority. An authority that resolves to a ``:Case`` id but carries no
        court or date is *not* good enough — it pins the output for human
        review exactly as an unresolved one does.
        """
        names = [str(src.get("title") or "").strip() for src in output.sources]
        names = [n for n in names if n]
        if not names:
            output.requires_review = True
            output.reasoning_trace[-1:] = [
                "No authorities were named by the model — nothing to ground; "
                "human review required (constitution §13)."
            ]
            return

        try:
            mapping = dict(await self._cite_resolver(names))
        except Exception as exc:
            logger.warning("authority grounding unavailable: %s", exc)
            output.requires_review = True
            output.reasoning_trace[-1:] = [
                "Citation resolver unavailable — authorities could not be "
                f"grounded against the knowledge graph ({type(exc).__name__}); "
                "human review required."
            ]
            return

        # Every name is looked up, not only the ones the alias resolver
        # missed: the resolver returns ids, and §13 needs the passage behind
        # the id to say which court decided what, and when.
        matched = await _name_lookup(names, self._get_name_retriever())
        for name, (case_id, _passage) in matched.items():
            if not mapping.get(name):
                mapping[name] = case_id

        output.sources = [
            {
                "title": name,
                "verified": bool(mapping.get(name)),
                "attribution": attribution_from_passage(
                    (matched.get(name) or (None, None))[1], jurisdiction
                ).model_dump(),
                "resolved_case_id": mapping.get(name),
            }
            for name in names
        ]
        still_unverified = sum(1 for name in names if not mapping.get(name))
        # §13: "resolved" and "attributed" are different guarantees, and either
        # gap needs a human before this output is relied on.
        unattributed = check_attribution(
            [{**src, "text": src["title"]} for src in output.sources]
        )
        output.requires_review = still_unverified > 0 or bool(unattributed)
        output.reasoning_trace[-1:] = [
            f"Grounded {len(names) - still_unverified}/{len(names)} authorities "
            "against the knowledge graph (alias resolver + case-name lookup)."
            + (
                f" {still_unverified} unresolved — human review required."
                if still_unverified
                else ""
            )
            + (
                " Attribution incomplete (constitution §13): "
                + "; ".join(unattributed[:5])
                + " — human review required."
                if unattributed
                else ""
            )
        ]

    def _delta_sink(self, input_data: dict[str, Any]) -> DeltaSink | None:
        """Relay generated deltas to this run's WebSocket group, or ``None``.

        The IRAC pass is the slowest interactive call this product makes —
        live xAI runs measured 56-103s — and until BL-20260905-11 the client
        saw nothing at all until it finished, because ``/api/analysis`` only
        emitted an ``agent_step`` event *after* each agent returned. With a
        ``stream_id`` the answer now arrives as it is written.

        Fire-and-forget, like every other event on this socket: a Redis outage
        must not fail an analysis that otherwise succeeded (spec 021 AC-2).
        """
        stream_key = str(input_data.get("stream_id") or "").strip()
        if not stream_key:
            return None
        from law_ai.agentsapi.streaming import emit_stream_event

        analysis_id = str(input_data.get("analysis_id") or "") or None
        state = {"chars": 0}

        async def sink(text: str, model: str | None = None) -> None:
            state["chars"] += len(text)
            payload: dict[str, Any] = {
                "type": "analysis_token",
                "agent": self.name,
                "text": text,
                "chars": state["chars"],
            }
            if analysis_id:
                payload["analysis_id"] = analysis_id
            if model:
                payload["model"] = model
            try:
                await emit_stream_event(stream_key, payload, source="analysis")
            except Exception:  # pragma: no cover - defensive
                logger.debug("analysis delta not delivered", exc_info=True)

        return sink

    async def _irac_text(
        self, prompt: str, input_data: dict[str, Any]
    ) -> tuple[str, str]:
        """The IRAC JSON plus the tier that served it, streamed when possible.

        Buffered by default (batch callers, tests, anything without a
        ``stream_id``); streamed through the same chain when the request
        carries one, so the person waiting sees tokens instead of a spinner
        (BL-20260905-11). Either way the caller parses one complete JSON
        payload — the deltas are progress, never the result.
        """
        # /api/analysis is a person waiting on a page; use the faster Grok id
        # when one is configured (BL-20260905-11).
        overrides = xai.interactive_overrides()
        sink = self._delta_sink(input_data)
        if sink is None:
            result = await llm.agenerate(
                prompt,
                system=_IRAC_SYSTEM,
                response_schema=_IRAC_SCHEMA,
                agent=self.name,
                models=overrides,
            )
            return result.text, result.model_label
        parts: list[str] = []
        label = "(provider chain)"
        async for chunk in llm.astream(
            prompt,
            system=_IRAC_SYSTEM,
            response_schema=_IRAC_SCHEMA,
            agent=self.name,
            models=overrides,
        ):
            parts.append(chunk.text)
            label = chunk.model_label
            await sink(chunk.text, chunk.model_label)
        return "".join(parts), label

    async def run(self, input_data: dict[str, Any]) -> IRACOutput:
        # Spec 027: LangGraph is the DEFAULT engine (AnalysisRequest defaults
        # use_langgraph=true). The explicit-false escape hatch runs the same
        # provider chain directly, without the graph's retrieval nodes.
        if input_data.get("use_langgraph"):
            return await self._run_via_langgraph(input_data)
        return await self._run_via_llm(input_data)

    async def _run_via_llm(self, input_data: dict[str, Any]) -> IRACOutput:
        """Real IRAC analysis through the shared provider chain (spec 034).

        Claude first, the Anthropic API key second, local Ollama last. Pinned
        with structured outputs so the Claude tiers return schema-valid JSON,
        and degrades to a clearly-labeled offline placeholder when the whole
        chain fails — never raising into the caller.
        """
        start = time.time()
        question = input_data.get("text") or input_data.get("question") or ""
        prompt = _build_irac_prompt(
            question,
            facts=str(input_data.get("facts") or ""),
            jurisdiction=str(input_data.get("jurisdiction") or ""),
        )
        try:
            text, model_used = await self._irac_text(prompt, input_data)
            output = _irac_from_payload(llm.loads_first_json(text), question)
            # Constitution §1: model-named authorities are not sources until
            # the graph confirms them (BL-20260615-03), and §13: they are not
            # authorities until they name a court and a date (BL-20260803-04).
            await self._ground_authorities(
                output, str(input_data.get("jurisdiction") or "") or None
            )
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
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

    async def _run_via_langgraph(self, input_data: dict[str, Any]) -> IRACOutput:
        """Spec 010 T-006: delegate to LegalWorkflow.

        BL-20260511-06 finished the backfill: the workflow's analyze node now
        returns the IRAC split (``issue``/``rule``/``conclusion``) next to the
        prose answer, so this maps real workflow content into every IRAC field
        — ``application`` from ``answer``, the rest from the split — instead of
        stubbing issue and rule. A model that omits part of the split leaves it
        empty and the placeholder below stands in, because an invented rule is
        worse than an honest "see the cited authorities".

        Per-citation §13 attribution (court, jurisdiction, decided_at,
        binding/persuasive) rides along on each source (BL-20260803-04), and
        deltas are relayed to the run's WebSocket group while the analyze node
        generates (BL-20260905-11).
        """
        question = input_data.get("text") or input_data.get("question") or ""

        # Resilience boundary (spec 027): as the DEFAULT engine this path must
        # never 500 the API. The readiness check is chain-aware
        # (BL-20260615-02): it only probes Ollama when Ollama is the sole
        # configured tier, so a Claude-only dev box runs the workflow instead
        # of being refused by a local reachability check that does not apply.
        ready, not_ready_reason = await _engine_ready()
        if not ready:
            output = _langgraph_fallback_irac(str(question), not_ready_reason)
            output.trace_id = provenance.log_agent_call(
                agent_name=self.name,
                input_data=input_data,
                output_data=output.model_dump(),
                model="fallback/offline",
                latency_ms=0.0,
                confidence=0.0,
            )
            return output

        thread_id = input_data.get("thread_id") or None
        resumed = False
        try:
            from law_ai.agents_runtime.graphs import LegalWorkflow

            async with _analysis_checkpointer() as saver:
                workflow = LegalWorkflow(
                    checkpointer=saver, on_delta=self._delta_sink(input_data)
                )
                if thread_id and saver is not None:
                    prior = await _thread_state_values(workflow, str(thread_id))
                    resumed = bool(prior)
                    if resumed:
                        # BL-20260905-81: refuse to silently rewrite the
                        # channels of a thread that was asked something else.
                        _check_thread_continuity(
                            str(thread_id),
                            prior,
                            question=str(question),
                            jurisdiction=input_data.get("jurisdiction"),
                        )
                result = await workflow.invoke(
                    question,
                    jurisdiction=input_data.get("jurisdiction"),
                    case_id=input_data.get("case_id"),
                    thread_id=str(thread_id) if thread_id else None,
                    # BL-20260817-05: when the caller says which matter this
                    # round belongs to, the retriever promotes the authorities
                    # that matter has already had verified. The API layer has
                    # already proved ownership; this just carries the id.
                    matter_id=_coerce_matter_id(input_data.get("matter_id")),
                )
        except ThreadDivergence:
            # Not an engine failure: the caller contradicted the thread they
            # named. Degrading here would hide a client bug behind an honest
            # -looking refusal, so it travels up to the view as a 409.
            raise
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
                # §13 (BL-20260803-04): the issuing authority the workflow
                # read off the :Case node this citation points at. Dropping it
                # here is what used to leave /api/analysis emitting statements
                # of law with no court, jurisdiction or date.
                "attribution": c.attribution or Attribution().model_dump(),
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
            # BL-20260511-06: prefer the workflow's own split; fall back to the
            # question / a pointer at the authorities when the model left one
            # empty, never to invented black-letter law.
            issue=result.issue or question[:200] or "(no question provided)",
            rule=result.rule or "See cited authorities below.",
            application=result.answer,
            conclusion=(
                f"{result.conclusion}\n\n{conclusion}"
                if result.conclusion
                else conclusion
            ),
            sources=sources,
            confidence=result.confidence,
            requires_review=result.human_approval_required,
            retrieval=result.retrieval_stats.model_dump(),
            resumed=resumed,
            reasoning_trace=[
                f"LangGraph thread {result.langgraph_thread_id}"
                + (" (resumed)" if resumed else ""),
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
