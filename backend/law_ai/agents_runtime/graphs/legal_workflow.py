"""LegalWorkflow — 3-node LangGraph: retrieve → analyze → cite_check.

Spec 010 FR-3. Designed to be safe to import even when the ``local-ai``
extra is not installed: the heavy ``langgraph`` / ``langchain-ollama``
imports are deferred until ``LegalWorkflow.invoke`` is actually called.

Tests can inject a fake ``llm_factory`` and ``cite_resolver`` to exercise
the node graph without Ollama or Neo4j running.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Protocol, TypedDict
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.provenance import logged_node
from law_ai.core.telemetry import phoenix_trace_url

logger = logging.getLogger("law_ai.graphs.legal_workflow")

PROMPT_VERSION = "1"


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class WorkflowCitation(BaseModel):
    text: str
    source_url: str | None = None
    source: str = Field(
        default="analyze",
        description="`analyze` for LLM-emitted, `ollama-hallucination-check` for unresolved.",
    )
    resolved_case_id: str | None = None


class RetrievalStats(BaseModel):
    """Coverage envelope for retrieval (constitution §13 "absence is reported").

    Lets reviewers distinguish "no results in our corpus" from "no such law"
    (BL-20260803-02): the queries actually issued, how many passages came
    back, which jurisdictions are actually represented, and whether the
    requested one is missing entirely.
    """

    queries: list[str] = Field(default_factory=list)
    result_count: int = 0
    lexical_count: int = 0
    expanded_count: int = Field(
        default=0, description="Passages added by CITES graph expansion."
    )
    jurisdiction_requested: str | None = None
    jurisdictions_present: list[str] = Field(default_factory=list)
    jurisdiction_absent: bool = Field(
        default=False,
        description="True when nothing came back from the requested jurisdiction.",
    )
    coverage_note: str = Field(
        default="",
        description="Human-readable caveat about corpus coverage for this run.",
    )


class LegalWorkflowOutput(BaseModel):
    answer: str
    citations: list[WorkflowCitation] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    human_approval_required: bool = False
    retrieval_stats: RetrievalStats = Field(default_factory=RetrievalStats)
    trace_id: str | None = None
    phoenix_trace_url: str | None = None
    langgraph_thread_id: str | None = None
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Workflow state
# ---------------------------------------------------------------------------


class LegalWorkflowState(TypedDict, total=False):
    question: str
    jurisdiction: str | None
    case_id: str | None
    queries: list[str]
    retrieved: list[dict[str, Any]]
    # Coverage detail published by retrievers that expose `last_coverage`
    # (see agents_runtime.tools.graph_rag) — merged into RetrievalStats.
    retrieval_coverage: dict[str, Any]
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    human_approval_required: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Pluggable collaborators (DI seams for tests)
# ---------------------------------------------------------------------------


class _LLMLike(Protocol):
    async def ainvoke(self, prompt: str) -> Any:  # pragma: no cover - structural
        ...


CiteResolver = Callable[[list[str]], Awaitable[dict[str, str | None]]]
Retriever = Callable[[LegalWorkflowState], Awaitable[list[dict[str, Any]]]]


def _default_llm_factory() -> _LLMLike:
    """Build the shared retry-wrapped ``ChatOllama`` runnable (spec 027).

    Routed through :mod:`law_ai.agents_runtime.llm` so every agent shares one
    LangChain transport with tenacity-backed retries (constitution §8).
    """
    from law_ai.agents_runtime.llm import build_chat_ollama

    runnable: _LLMLike = build_chat_ollama()
    return runnable


async def _default_cite_resolver(citations: list[str]) -> dict[str, str | None]:
    """Resolve normalized citations against Neo4j via spec 002's resolver."""
    if not citations:
        return {}
    from law_ai.core.neo4j.citation_resolver import resolve_citations
    from law_ai.core.neo4j.driver import get_neo4j_driver

    driver = get_neo4j_driver()
    async with driver.session() as session:
        return await resolve_citations(session, citations)


def _build_default_retriever() -> Retriever:
    """Real hybrid GraphRAG retriever (BL-20260810-01).

    Lexical fulltext over ``:Case``/``:StatuteSection`` plus one hop of
    ``CITES`` expansion, every query logged via ``log_graph_query``. It
    yields an empty list (⇒ the refusal path) only when Neo4j itself is
    unreachable — an honest "we retrieved nothing", never a fabrication.
    """
    from law_ai.agents_runtime.tools.graph_rag import build_default_retriever

    retriever: Retriever = build_default_retriever()
    return retriever


# ---------------------------------------------------------------------------
# JSON-from-LLM helpers
# ---------------------------------------------------------------------------


def _coerce_text(message: Any) -> str:
    """Pull the textual payload out of whatever the LLM returns."""
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # pragma: no cover - LangChain message parts
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(message)


def _parse_json(text: str, default: dict[str, Any]) -> dict[str, Any]:
    """Best-effort JSON extraction. Tolerates fenced code blocks + prose.

    Always returns a dict: a response that parses to a JSON array/scalar is
    as unusable as unparseable text, so both fall back to ``default``.
    """
    if not text:
        return default
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # Drop optional language hint on the first line.
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fall back: find the first {...} block.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return default


def _clamp01(value: Any, default: float = 0.5) -> float:
    """Coerce an LLM-supplied confidence to a float in [0, 1]."""
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# LegalWorkflow
# ---------------------------------------------------------------------------


class LegalWorkflow:
    """Stateful 3-node legal analysis workflow.

    Use :py:meth:`invoke` for one-shot runs. State is persisted via the
    checkpointer returned by :func:`app.agents.graphs.runtime.build_checkpointer`,
    so a backend restart can resume an in-flight workflow by reusing the
    same ``thread_id`` (NFR-RESILIENCE-1, AC-3).
    """

    def __init__(
        self,
        *,
        llm_factory: Callable[[], _LLMLike] | None = None,
        cite_resolver: CiteResolver | None = None,
        retriever: Retriever | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._llm_factory = llm_factory or _default_llm_factory
        self._cite_resolver = cite_resolver or _default_cite_resolver
        # Built eagerly (no connection is opened until first query) so the
        # instance can publish `last_coverage` after each retrieval.
        self._retriever = retriever or _build_default_retriever()
        self._checkpointer = checkpointer

    # -- nodes -------------------------------------------------------------

    @logged_node(
        "retrieve",
        model="(ollama)",
        prompt_id="legal_workflow.retrieve",
        prompt_version=PROMPT_VERSION,
    )
    async def _retrieve(self, state: LegalWorkflowState) -> dict[str, Any]:
        question = state.get("question", "")
        if not question:
            return {"queries": [], "retrieved": []}
        llm = self._llm_factory()
        prompt = (
            "You are a legal research assistant. Draft up to 3 short search "
            "queries (Cypher-friendly) for the question below. Return ONLY "
            'JSON: {"queries": [str], "rationale": str}.\n\n'
            f"Jurisdiction: {state.get('jurisdiction') or 'any'}\n"
            f"Question: {question}"
        )
        raw = _coerce_text(await llm.ainvoke(prompt))
        parsed = _parse_json(raw, {"queries": [question], "rationale": "fallback"})
        raw_queries = parsed.get("queries") or []
        if not isinstance(raw_queries, list):
            raw_queries = []
        queries = [str(q)[:120] for q in raw_queries][:3] or [question]
        retrieved = await self._retriever({**state, "queries": queries})
        out: dict[str, Any] = {"queries": queries, "retrieved": retrieved}
        # Retrievers may publish a richer coverage envelope (result mix,
        # jurisdictions actually represented). Returning it here is what
        # merges it into graph state — mutating the input state would not.
        coverage = getattr(self._retriever, "last_coverage", None)
        if coverage is not None:
            out["retrieval_coverage"] = {
                "lexical_count": getattr(coverage, "lexical_count", 0),
                "expanded_count": getattr(coverage, "expanded_count", 0),
                "jurisdictions_present": list(
                    getattr(coverage, "jurisdictions_present", [])
                ),
                "jurisdiction_absent": bool(
                    getattr(coverage, "jurisdiction_absent", False)
                ),
                "coverage_note": coverage.note() if hasattr(coverage, "note") else "",
            }
        return out

    @logged_node(
        "analyze",
        model="(ollama)",
        prompt_id="legal_workflow.analyze",
        prompt_version=PROMPT_VERSION,
    )
    async def _analyze(self, state: LegalWorkflowState) -> dict[str, Any]:
        retrieved = state.get("retrieved") or []
        question = state.get("question", "")
        if not retrieved:
            return {
                "answer": "Insufficient sources to answer confidently: "
                "no retrieved passages were available.",
                "citations": [],
                "confidence": 0.2,
            }
        llm = self._llm_factory()
        # Every passage carries its issuing authority so the model can
        # attribute propositions (constitution §13) instead of stating
        # unsourced "the law".
        passages = "\n\n".join(
            f"[{idx + 1}] {item.get('title', 'Untitled')}"
            + (f" — {item['court']}" if item.get("court") else "")
            + (f" ({item['decided_at']})" if item.get("decided_at") else "")
            + f"\n{str(item.get('snippet', ''))[:500]}"
            + f"\nURL: {item.get('source_url') or ''}"
            for idx, item in enumerate(retrieved)
        )
        prompt = (
            "Answer the question using ONLY the passages below. Cite every "
            "legal proposition, naming the issuing authority (court and date) "
            "for each. If the passages do not answer the question, say so "
            "instead of answering from general knowledge. Return strict JSON "
            "with keys answer, citations (array of {text, source_url}), "
            "confidence (0..1).\n\n"
            f"Question: {question}\n\nPassages:\n{passages}"
        )
        raw = _coerce_text(await llm.ainvoke(prompt))
        parsed = _parse_json(
            raw,
            {
                "answer": "Insufficient sources to answer confidently: "
                "model returned an unparseable response.",
                "citations": [],
                "confidence": 0.2,
            },
        )
        raw_citations = parsed.get("citations") or []
        if not isinstance(raw_citations, list):
            raw_citations = []
        citations = [
            {
                "text": str(c.get("text", "")).strip(),
                "source_url": c.get("source_url"),
            }
            for c in raw_citations
            # Models sometimes emit bare strings or nulls in the array;
            # only dict entries carry the {text, source_url} shape we need.
            if isinstance(c, dict) and str(c.get("text", "")).strip()
        ]
        return {
            "answer": str(parsed.get("answer", "")).strip(),
            "citations": citations,
            "confidence": _clamp01(parsed.get("confidence")),
        }

    @logged_node(
        "cite_check",
        model="deterministic",
        prompt_id="legal_workflow.cite_check",
        prompt_version=PROMPT_VERSION,
    )
    async def _cite_check(self, state: LegalWorkflowState) -> dict[str, Any]:
        candidates = state.get("citations") or []
        if not candidates:
            # An answer with zero citations cannot satisfy the constitution
            # §13 attribution rule (every legal proposition names its issuing
            # authority) — and the refusal path lands here too. Either way a
            # human must look before this output is relied on.
            return {"citations": [], "human_approval_required": True}
        normalized = [str(c.get("text", "")).strip() for c in candidates]
        try:
            mapping = await self._cite_resolver(normalized)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cite_check resolver failed: %s", exc)
            mapping = {n: None for n in normalized}
        verified: list[dict[str, Any]] = []
        unverified = 0
        for cit in candidates:
            text = str(cit.get("text", "")).strip()
            resolved = mapping.get(text)
            if resolved:
                verified.append(
                    {**cit, "source": "analyze", "resolved_case_id": resolved}
                )
            else:
                unverified += 1
                verified.append(
                    {
                        **cit,
                        "source": "ollama-hallucination-check",
                        "resolved_case_id": None,
                    }
                )
        return {
            "citations": verified,
            "human_approval_required": unverified > 0,
        }

    # -- public API --------------------------------------------------------

    def _build_graph(self, checkpointer: Any) -> Any:
        from langgraph.graph import END, StateGraph

        builder: Any = StateGraph(LegalWorkflowState)
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("analyze", self._analyze)
        builder.add_node("cite_check", self._cite_check)
        builder.set_entry_point("retrieve")
        builder.add_edge("retrieve", "analyze")
        builder.add_edge("analyze", "cite_check")
        builder.add_edge("cite_check", END)
        if checkpointer is not None:
            return builder.compile(checkpointer=checkpointer)
        return builder.compile()

    async def invoke(
        self,
        question: str,
        *,
        jurisdiction: str | None = None,
        case_id: str | None = None,
        thread_id: str | None = None,
        checkpointer: Any | None = None,
    ) -> LegalWorkflowOutput:
        """Run the workflow end-to-end and return the structured output."""
        from opentelemetry import trace as otel_trace

        thread = thread_id or f"lwf-{secrets.token_hex(6)}"
        config = {"configurable": {"thread_id": thread}}
        state: LegalWorkflowState = {
            "question": question,
            "jurisdiction": jurisdiction,
            "case_id": case_id,
        }
        cp = checkpointer if checkpointer is not None else self._checkpointer
        graph = self._build_graph(cp)

        tracer = otel_trace.get_tracer("law_ai.legal_workflow")
        started = time.perf_counter()
        with tracer.start_as_current_span("legal_workflow.invoke") as span:
            span.set_attribute("legal_workflow.thread_id", thread)
            span.set_attribute("legal_workflow.model", settings.OLLAMA_DEFAULT_MODEL)
            result = await graph.ainvoke(state, config=config)
            span_ctx = span.get_span_context()
            trace_id = f"{span_ctx.trace_id:032x}" if span_ctx.is_valid else None
        latency_ms = (time.perf_counter() - started) * 1000.0

        citations = [WorkflowCitation(**c) for c in (result.get("citations") or [])]
        retrieved = result.get("retrieved") or []
        jurisdiction_requested = result.get("jurisdiction")
        cov = result.get("retrieval_coverage") or {}
        default_note = (
            "No passages were retrieved from the knowledge graph. Absence "
            "of results in this corpus does NOT mean no such law exists."
            if not retrieved
            else f"{len(retrieved)} passage(s) retrieved from the "
            "knowledge graph; coverage is limited to the ingested corpus."
        )
        retrieval_stats = RetrievalStats(
            queries=[str(q) for q in (result.get("queries") or [])],
            result_count=len(retrieved),
            lexical_count=int(cov.get("lexical_count", len(retrieved))),
            expanded_count=int(cov.get("expanded_count", 0)),
            jurisdiction_requested=jurisdiction_requested,
            jurisdictions_present=[
                str(j) for j in (cov.get("jurisdictions_present") or [])
            ],
            jurisdiction_absent=bool(cov.get("jurisdiction_absent", False)),
            coverage_note=str(cov.get("coverage_note") or default_note),
        )
        return LegalWorkflowOutput(
            answer=result.get("answer", ""),
            citations=citations,
            confidence=_clamp01(result.get("confidence"), default=0.0),
            human_approval_required=bool(result.get("human_approval_required", False)),
            retrieval_stats=retrieval_stats,
            trace_id=trace_id,
            phoenix_trace_url=phoenix_trace_url(trace_id),
            langgraph_thread_id=thread,
            latency_ms=round(latency_ms, 2),
        )

    async def get_state(self, thread_id: str) -> Any:
        """Inspect persisted state for ``thread_id`` (NFR-RESILIENCE-1)."""
        cp = self._checkpointer
        graph = self._build_graph(cp)
        return await graph.aget_state({"configurable": {"thread_id": thread_id}})
