"""LegalWorkflow — 3-node LangGraph: retrieve → analyze → cite_check.

Spec 010 FR-3. Designed to be safe to import even when the ``local-ai``
extra is not installed: the heavy ``langgraph`` import is deferred until
``LegalWorkflow.invoke`` is actually called. LLM access goes through the
unified audited client in ``lawgraph.core.llm`` (spec 024).

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

from lawgraph.core.settings_proxy import settings_proxy as settings
from lawgraph.core.provenance import logged_node
from lawgraph.core.telemetry import phoenix_trace_url

logger = logging.getLogger("lawgraph.graphs.legal_workflow")

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


class LegalWorkflowOutput(BaseModel):
    answer: str
    citations: list[WorkflowCitation] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    human_approval_required: bool = False
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
    """Build the unified audited Ollama client (spec 024 FR-2).

    Returns an adapter satisfying the ``_LLMLike`` protocol so node code
    is agnostic to the transport. Retry, timeout, and provenance live in
    :class:`lawgraph.core.llm.LLMClient`.
    """
    from lawgraph.core.llm import LLMClientAdapter

    return LLMClientAdapter(temperature=0.0, caller="legal_workflow")


async def _default_cite_resolver(citations: list[str]) -> dict[str, str | None]:
    """Resolve normalized citations against Neo4j via spec 002's resolver."""
    if not citations:
        return {}
    from lawgraph.core.neo4j.citation_resolver import resolve_citations
    from lawgraph.core.neo4j.driver import get_neo4j_driver

    driver = get_neo4j_driver()
    async with driver.session() as session:
        return await resolve_citations(session, citations)


async def _default_retriever(
    state: LegalWorkflowState,
) -> list[dict[str, Any]]:
    """Stub retriever — real GraphRAG lands in BL-20260502-04 follow-up.

    Returns an empty list so the ``analyze`` node will trigger the spec's
    insufficient-sources refusal path. Tests inject a richer retriever.
    """
    return []


def _node_prompt(name: str) -> Any:
    """Load the versioned prompt template for a workflow node (spec 024 FR-5).

    Templates live in ``agents_runtime/prompts/legal_workflow/``; the full
    rendered prompt is hashed into the provenance event by the LLM client.
    """
    from lawgraph.agents_runtime.prompts.loader import load_prompt

    return load_prompt(f"legal_workflow/{name}", version=PROMPT_VERSION)


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
    """Best-effort JSON extraction. Tolerates fenced code blocks + prose."""
    if not text:
        return default
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # Drop optional language hint on the first line.
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back: find the first {...} block.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
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
        self._retriever = retriever or _default_retriever
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
        prompt = _node_prompt("retrieve").render(
            jurisdiction=state.get("jurisdiction") or "any",
            question=question,
        )
        raw = _coerce_text(await llm.ainvoke(prompt))
        parsed = _parse_json(raw, {"queries": [question], "rationale": "fallback"})
        queries = [str(q)[:120] for q in (parsed.get("queries") or [])][:3] or [
            question
        ]
        retrieved = await self._retriever({**state, "queries": queries})
        return {"queries": queries, "retrieved": retrieved}

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
        passages = "\n\n".join(
            f"[{idx + 1}] {item.get('title', 'Untitled')} — "
            f"{item.get('snippet', '')[:500]}\nURL: {item.get('source_url') or ''}"
            for idx, item in enumerate(retrieved)
        )
        prompt = _node_prompt("analyze").render(
            question=question,
            passages=passages,
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
        citations = [
            {
                "text": str(c.get("text", "")).strip(),
                "source_url": c.get("source_url"),
            }
            for c in (parsed.get("citations") or [])
            if str(c.get("text", "")).strip()
        ]
        return {
            "answer": str(parsed.get("answer", "")).strip(),
            "citations": citations,
            "confidence": float(parsed.get("confidence", 0.5)),
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
            return {"citations": [], "human_approval_required": False}
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

        tracer = otel_trace.get_tracer("lawgraph.legal_workflow")
        started = time.perf_counter()
        with tracer.start_as_current_span("legal_workflow.invoke") as span:
            span.set_attribute("legal_workflow.thread_id", thread)
            span.set_attribute("legal_workflow.model", settings.OLLAMA_DEFAULT_MODEL)
            result = await graph.ainvoke(state, config=config)
            span_ctx = span.get_span_context()
            trace_id = f"{span_ctx.trace_id:032x}" if span_ctx.is_valid else None
        latency_ms = (time.perf_counter() - started) * 1000.0

        citations = [WorkflowCitation(**c) for c in (result.get("citations") or [])]
        return LegalWorkflowOutput(
            answer=result.get("answer", ""),
            citations=citations,
            confidence=float(result.get("confidence", 0.0)),
            human_approval_required=bool(result.get("human_approval_required", False)),
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
