"""TopicFrontier — 4-node LangGraph workflow (spec 018 T-007, spec 027).

Nodes:

    scan_graph → prioritize → dispatch → summarize

Spec 027 made this a real compiled ``langgraph.graph.StateGraph`` (the
sequential claim in spec 018 was aspirational until then). When the
``local-ai`` extra is not installed the workflow degrades to direct
sequential async execution of the same node functions, so a bare install
still runs autonomy cycles.

``scan_graph``   reads two Cypher helpers (``list_orphan_citations``,
                 ``list_under_cited_jurisdictions``) and populates the
                 state with gap data.

``prioritize``   calls Ollama with the versioned prompt template and
                 returns up to 3 ranked fetch targets.

``dispatch``     iterates the targets, awaits ``SOURCE_REGISTRY[name].afetch``
                 for each, then routes every :class:`RawDoc` through
                 ``IngestionScout.run_and_commit``.  **Never** writes Neo4j
                 directly (constitution §12 invariant I1).

``summarize``    logs the full cycle summary via ``core.provenance`` and
                 returns a :class:`TopicFrontierOutput`.

``prioritize`` branches: an empty ranking routes straight to ``summarize``
rather than walking ``dispatch`` over nothing. ``prioritize`` and ``dispatch``
carry a ``RetryPolicy`` (3 attempts) because both are network-bound, and the
graph compiles with an injected checkpointer when the caller supplies one
(BL-20260511-31).

Design notes:
- Every LLM call is logged; every Neo4j write goes through
  ``IngestionScout.run_and_commit`` (which carries ``agent_version``).
- ``human_approval_required`` is set on any adapter whose
  ``requires_human_approval`` flag is True.
- Provider/model selection via ``law_ai.core.config`` only.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from law_ai.core import audit_jsonl
from law_ai.core.provenance import provenance
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.graphs.topic_frontier")

AGENT_VERSION = "law_ai.agents_runtime.graphs.topic_frontier.v1"
PROMPT_VERSION = "1"

_PROMPT_PATH = (
    Path(__file__).parent.parent / "prompts" / "topic_frontier_prioritize.v1.md"
)

# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class FetchTarget(BaseModel):
    """A single ranked item returned by the ``prioritize`` node."""

    query: str
    jurisdiction: str = "*"
    reason: str = ""
    priority: int = 1


class DispatchResult(BaseModel):
    """Summary for one ``RawDoc`` routed through ``IngestionScout``."""

    source_name: str
    source_url: str
    committed: bool
    confidence: float


class TopicFrontierOutput(BaseModel):
    """Structured output of a completed ``TopicFrontier`` run."""

    trace_id: str
    targets: list[FetchTarget] = Field(default_factory=list)
    dispatched: list[DispatchResult] = Field(default_factory=list)
    latency_ms: float = 0.0
    human_approval_required: bool = False


# ---------------------------------------------------------------------------
# Workflow state
# ---------------------------------------------------------------------------


class TopicFrontierState(TypedDict, total=False):
    trace_id: str
    orphan_citations: list[str]
    under_cited_jurisdictions: list[str]
    targets: list[dict[str, Any]]
    dispatched: list[dict[str, Any]]
    human_approval_required: bool
    latency_ms: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _call_llm(prompt: str, *, model: str, base_url: str, timeout: int = 120) -> str:
    """Generate text through the shared provider chain (spec 034).

    Keeps the ``RuntimeError`` contract the ``llm_caller`` DI seam relies on,
    but the request now runs the Claude-first chain and only reaches Ollama as
    the last fallback. ``model`` scopes the Ollama tier only; ``base_url`` and
    ``timeout`` are accepted for signature compatibility (the Ollama transport
    reads both from settings).
    """
    from law_ai.core import llm

    try:
        return llm.generate(
            prompt, models={"ollama": model}, agent="topic_frontier"
        ).text
    except Exception as exc:
        raise RuntimeError(f"no LLM provider could serve the request: {exc}") from exc


async def _acall_llm(prompt: str, *, model: str) -> str:
    """Async twin of :func:`_call_llm` for the graph nodes.

    ``_node_prioritize`` runs inside the event loop, where the sync entry point
    refuses to run (it would block every other request on the worker). Same
    ``RuntimeError`` contract as the sync helper.
    """
    from law_ai.core import llm

    try:
        result = await llm.agenerate(
            prompt, models={"ollama": model}, agent="topic_frontier"
        )
    except Exception as exc:
        raise RuntimeError(f"no LLM provider could serve the request: {exc}") from exc
    return result.text


def _parse_targets(llm_output: str) -> list[dict[str, Any]]:
    """Extract the JSON array from LLM output; return [] on any parse failure."""
    text = llm_output.strip()
    # Strip optional markdown fences.
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed[:3]
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "topic_frontier: could not parse prioritize output: %r", text[:200]
        )
    return []


def _pick_adapter(
    registry: dict[str, Any], allowed_sources: list[str], jurisdiction: str
) -> Any | None:
    """Return the best adapter from *registry* for *jurisdiction*.

    Tries an exact jurisdiction match first; falls back to the first
    adapter in *allowed_sources* that is present in the registry.
    """
    for name, cand in registry.items():
        if name not in allowed_sources:
            continue
        # Match when the *adapter's* jurisdiction is '*' (wildcard) or equals
        # the requested jurisdiction.  The previous condition was inverted —
        # it tested whether the *request* jurisdiction was in the adapter's
        # jurisdiction string, which prevented wildcard adapters from matching.
        if getattr(cand, "jurisdiction", "*") in ("*", jurisdiction):
            return cand
    for name in allowed_sources:
        if name in registry:
            return registry[name]
    return None


async def _adapter_docs(adapter: Any, query: str, *, limit: int) -> list[Any]:
    """Fetch documents from *adapter* without nesting event loops.

    BL-20260511-08: this function runs inside the autonomy loop, and the
    adapters' old sync ``fetch`` called ``asyncio.run`` internally — which
    raises ``RuntimeError`` from a running loop. The bare ``except`` below
    logged that as "fetch failed", so every real ``corpus_growth`` dispatch
    silently fetched nothing. Prefer the adapter's ``afetch`` coroutine;
    fall back to running a duck-typed adapter's sync ``fetch`` in a worker
    thread (test doubles, third-party adapters).
    """
    afetch = getattr(adapter, "afetch", None)
    if afetch is not None and inspect.iscoroutinefunction(afetch):
        return list(await afetch(query, limit=limit))
    return list(await asyncio.to_thread(adapter.fetch, query, limit=limit))


async def _dispatch_target(
    scout: Any,
    adapter: Any,
    query: str,
    dispatched: list[dict[str, Any]],
    *,
    force_quarantine: bool = False,
) -> list[dict[str, Any]]:
    """Fetch docs from *adapter* and commit each through *scout*.

    When *force_quarantine* is True (set for adapters whose
    ``requires_human_approval`` flag is True), every document is routed
    to the HITL queue regardless of confidence score.

    Returns the (potentially extended) *dispatched* list.
    """
    try:
        docs = list(await _adapter_docs(adapter, query, limit=5))
    except Exception as exc:
        logger.warning("topic_frontier.dispatch: fetch failed: %s", exc)
        return dispatched
    for doc in docs:
        try:
            result = await scout.run_and_commit(
                {
                    "id": doc.source_url,
                    "case_name": doc.title,
                    "plain_text": doc.text,
                    "absolute_url": doc.source_url,
                    # BL-20260602-07: keep the originating adapter on the
                    # payload so PendingReview.source and the audit trail name
                    # the real source instead of a hardcoded "courtlistener".
                    "source_name": getattr(doc, "source_name", None),
                    # BL-20260803-01: adapters that know the record's own
                    # outcome text put it on RawDoc.metadata; forward it so
                    # the scout's deterministic mapper can see it. Adapters
                    # that do not simply leave both keys None.
                    "disposition": (getattr(doc, "metadata", None) or {}).get(
                        "disposition"
                    ),
                    "posture": (getattr(doc, "metadata", None) or {}).get("posture"),
                },
                force_quarantine=force_quarantine,
            )
            dispatched.append(
                {
                    "source_name": doc.source_name,
                    "source_url": doc.source_url,
                    "committed": result.get("committed", False),
                    "confidence": result.get("confidence", 0.0),
                }
            )
        except Exception as exc:
            logger.warning("topic_frontier.dispatch: run_and_commit failed: %s", exc)
    return dispatched


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def _node_scan_graph(
    state: TopicFrontierState,
    *,
    neo4j_session_factory: Any = None,
) -> TopicFrontierState:
    """Read gap data from Neo4j; injectable factory for tests."""
    if neo4j_session_factory is None:
        from law_ai.core.neo4j.driver import get_neo4j_driver
        from law_ai.core.neo4j import queries as neo4j_queries

        driver = get_neo4j_driver()
        async with driver.session() as session:
            orphans = await neo4j_queries.list_orphan_citations(session, limit=20)
            under = await neo4j_queries.list_under_cited_jurisdictions(
                session, limit=10
            )
    else:
        async with neo4j_session_factory() as session:
            from law_ai.core.neo4j import queries as neo4j_queries

            orphans = await neo4j_queries.list_orphan_citations(session, limit=20)
            under = await neo4j_queries.list_under_cited_jurisdictions(
                session, limit=10
            )

    return {
        **state,
        "orphan_citations": orphans,
        "under_cited_jurisdictions": under,
    }


async def _node_prioritize(
    state: TopicFrontierState,
    *,
    llm_caller: Any = None,
) -> TopicFrontierState:
    """Rank fetch targets via the provider chain; injectable for tests."""
    prompt_template = _load_prompt()
    user_data = json.dumps(
        {
            "orphan_citations": state.get("orphan_citations", []),
            "under_cited_jurisdictions": state.get("under_cited_jurisdictions", []),
        },
        indent=2,
    )
    full_prompt = f"{prompt_template}\n\n## Data\n\n{user_data}"

    model: str = settings.OLLAMA_DEFAULT_MODEL
    base_url: str = settings.OLLAMA_BASE_URL

    llm_started = time.monotonic()
    if llm_caller is not None:
        raw = llm_caller(full_prompt, model=model, base_url=base_url)
    else:
        raw = await _acall_llm(full_prompt, model=model)
    llm_latency_ms = (time.monotonic() - llm_started) * 1000.0

    targets = _parse_targets(raw)

    # Constitution §4: the LLM call itself goes through core.provenance
    # (model + latency + reproducible input hash), not just the summary
    # event below.
    provenance.log_agent_call(
        agent_name="TopicFrontier.prioritize",
        input_data={
            "trace_id": state.get("trace_id", ""),
            "orphan_citations_count": len(state.get("orphan_citations", [])),
            "under_cited_count": len(state.get("under_cited_jurisdictions", [])),
        },
        output_data={"targets": targets},
        model=model,
        latency_ms=llm_latency_ms,
        prompt_id="topic_frontier_prioritize",
        prompt_version=PROMPT_VERSION,
    )
    audit_jsonl.record(
        {
            "type": "topic_frontier.prioritize",
            "trace_id": state.get("trace_id", ""),
            "source": "autonomy",
            "confidence": 1.0,
            "agent_version": AGENT_VERSION,
            "prompt_version": PROMPT_VERSION,
            "targets_count": len(targets),
        }
    )

    return {**state, "targets": targets}


async def _node_dispatch(
    state: TopicFrontierState,
    *,
    registry: dict[str, Any] | None = None,
    scout_factory: Any = None,
) -> TopicFrontierState:
    """Route each target through SOURCE_REGISTRY + IngestionScout."""
    if registry is None:
        from law_ai.ingestionapp.sources import SOURCE_REGISTRY

        registry = SOURCE_REGISTRY

    if scout_factory is None:
        from law_ai.ingestionapp.services.scout import IngestionScout

        scout_factory = IngestionScout

    dispatched: list[dict[str, Any]] = []
    human_approval_required = False

    allowed_sources: list[str] = list(getattr(settings, "AUTONOMY_ALLOWED_SOURCES", []))

    for target in state.get("targets", []):
        jurisdiction = target.get("jurisdiction", "*")
        query = target.get("query", "")

        adapter = _pick_adapter(registry, allowed_sources, jurisdiction)
        if adapter is None:
            logger.warning(
                "topic_frontier.dispatch: no allowed adapter for target %r", target
            )
            continue

        if getattr(adapter, "requires_human_approval", False):
            human_approval_required = True

        # BL-20260602-07: an adapter may declare its own extractor; the
        # default IngestionScout stays the fallback.
        adapter_extractor = getattr(adapter, "extractor", None)
        scout = (
            adapter_extractor()
            if isinstance(adapter_extractor, type)
            else scout_factory()
        )
        dispatched = await _dispatch_target(
            scout,
            adapter,
            query,
            dispatched,
            force_quarantine=getattr(adapter, "requires_human_approval", False),
        )

    return {
        **state,
        "dispatched": dispatched,
        "human_approval_required": human_approval_required,
    }


def _route_after_prioritize(state: TopicFrontierState) -> str:
    """Conditional edge: skip ``dispatch`` when there is nothing to fetch.

    ``prioritize`` legitimately returns an empty ranking when the graph has no
    gaps (or the model refused). Walking ``dispatch`` in that case burns an
    adapter loop for nothing, so the graph branches straight to ``summarize``.
    """
    return "dispatch" if state.get("targets") else "summarize"


async def _node_summarize(state: TopicFrontierState) -> TopicFrontierState:
    """Log final provenance event; return completed state."""
    audit_jsonl.record(
        {
            "type": "topic_frontier.summarize",
            "trace_id": state.get("trace_id", ""),
            "source": "autonomy",
            "confidence": 1.0,
            "agent_version": AGENT_VERSION,
            "targets_count": len(state.get("targets", [])),
            "dispatched_count": len(state.get("dispatched", [])),
            "human_approval_required": state.get("human_approval_required", False),
        }
    )
    return state


# ---------------------------------------------------------------------------
# TopicFrontier class
# ---------------------------------------------------------------------------


class TopicFrontier:
    """Stateful LangGraph workflow: scan_graph → prioritize → dispatch → summarize.

    DI seams are exposed via constructor kwargs so tests never need Ollama,
    Neo4j, or IngestionScout running.

    :param neo4j_session_factory: async context-manager factory for Neo4j
        sessions.  ``None`` → use ``get_neo4j_driver``.
    :param llm_caller: callable with signature
        ``(prompt, *, model, base_url) -> str``.  ``None`` → real Ollama.
    :param registry: source adapter dict override.  ``None`` → ``SOURCE_REGISTRY``.
    :param scout_factory: callable that returns an ``IngestionScout``.
    :param checkpointer: LangGraph ``BaseCheckpointSaver`` to compile the graph
        with (BL-20260511-31).  ``None`` → no persistence, same as before.
        Callers own the saver's lifecycle — see
        ``law_ai.agents_runtime.graphs.runtime.build_checkpointer``.
    """

    human_approval_required: bool = False

    def __init__(
        self,
        *,
        neo4j_session_factory: Any = None,
        llm_caller: Any = None,
        registry: dict[str, Any] | None = None,
        scout_factory: Any = None,
        checkpointer: Any = None,
    ) -> None:
        self._neo4j_session_factory = neo4j_session_factory
        self._llm_caller = llm_caller
        self._registry = registry
        self._scout_factory = scout_factory
        self._checkpointer = checkpointer

    def _build_graph(self) -> Any:
        """Compile the real LangGraph ``StateGraph`` (spec 027).

        Node functions keep their DI-kwarg signatures for direct unit
        testing; thin async closures bind the injected collaborators so each
        graph node takes only ``state``.

        BL-20260511-31 realized the three gains the migration was meant to
        buy: the graph compiles with the injected ``checkpointer`` when one is
        supplied, the two I/O-bound nodes (``prioritize``, ``dispatch``) carry
        a :class:`~langgraph.types.RetryPolicy`, and a conditional edge after
        ``prioritize`` short-circuits to ``summarize`` when the ranking is
        empty.

        Raises:
            ImportError: when the ``local-ai`` extra (langgraph) is missing —
                ``run`` falls back to sequential execution.
        """
        from langgraph.graph import END, StateGraph
        from langgraph.types import RetryPolicy

        async def scan_graph(state: TopicFrontierState) -> TopicFrontierState:
            return await _node_scan_graph(
                state, neo4j_session_factory=self._neo4j_session_factory
            )

        async def prioritize(state: TopicFrontierState) -> TopicFrontierState:
            return await _node_prioritize(state, llm_caller=self._llm_caller)

        async def dispatch(state: TopicFrontierState) -> TopicFrontierState:
            return await _node_dispatch(
                state, registry=self._registry, scout_factory=self._scout_factory
            )

        # Network-bound nodes: an LLM hiccup or a flaky source adapter should
        # not lose a whole autonomy cycle.  scan_graph/summarize stay
        # un-retried (a Cypher failure is deterministic; summarize is a log).
        retry = RetryPolicy(max_attempts=3)

        builder: Any = StateGraph(TopicFrontierState)
        builder.add_node("scan_graph", scan_graph)
        builder.add_node("prioritize", prioritize, retry_policy=retry)
        builder.add_node("dispatch", dispatch, retry_policy=retry)
        builder.add_node("summarize", _node_summarize)
        builder.set_entry_point("scan_graph")
        builder.add_edge("scan_graph", "prioritize")
        builder.add_conditional_edges(
            "prioritize",
            _route_after_prioritize,
            {"dispatch": "dispatch", "summarize": "summarize"},
        )
        builder.add_edge("dispatch", "summarize")
        builder.add_edge("summarize", END)
        if self._checkpointer is not None:
            return builder.compile(checkpointer=self._checkpointer)
        return builder.compile()

    async def _run_sequential(self, state: TopicFrontierState) -> TopicFrontierState:
        """Fallback path for bare installs without the ``local-ai`` extra.

        Mirrors the compiled graph exactly, conditional edge included, so the
        two paths cannot drift.
        """
        state = await _node_scan_graph(
            state, neo4j_session_factory=self._neo4j_session_factory
        )
        state = await _node_prioritize(state, llm_caller=self._llm_caller)
        if _route_after_prioritize(state) == "dispatch":
            state = await _node_dispatch(
                state, registry=self._registry, scout_factory=self._scout_factory
            )
        return await _node_summarize(state)

    async def run(
        self, *, trace_id: str | None = None, thread_id: str | None = None
    ) -> TopicFrontierOutput:
        """Execute the 4-node graph and return :class:`TopicFrontierOutput`.

        Uses the compiled LangGraph ``StateGraph`` when available; degrades
        to sequential execution of the same nodes on bare installs.

        :param thread_id: checkpointer thread to resume/record under. Only
            meaningful when the instance was built with a ``checkpointer``;
            defaults to ``trace_id`` so every cycle gets its own thread.

        Example::

            tf = TopicFrontier(llm_caller=mock_llm, ...)
            output = await tf.run()
            assert output.dispatched  # at least one doc committed
        """
        t0 = time.monotonic()
        trace_id = trace_id or secrets.token_hex(16)

        state: TopicFrontierState = {
            "trace_id": trace_id,
            "orphan_citations": [],
            "under_cited_jurisdictions": [],
            "targets": [],
            "dispatched": [],
            "human_approval_required": False,
            "latency_ms": 0.0,
        }

        try:
            graph = self._build_graph()
        except ImportError:
            logger.info("topic_frontier: langgraph unavailable, running sequentially")
            state = await self._run_sequential(state)
        else:
            config: dict[str, Any] | None = None
            if self._checkpointer is not None:
                config = {"configurable": {"thread_id": thread_id or trace_id}}
            state = await graph.ainvoke(state, config)

        latency_ms = (time.monotonic() - t0) * 1000.0
        return TopicFrontierOutput(
            trace_id=trace_id,
            targets=[FetchTarget(**t) for t in state.get("targets", [])],
            dispatched=[DispatchResult(**d) for d in state.get("dispatched", [])],
            latency_ms=latency_ms,
            human_approval_required=state.get("human_approval_required", False),
        )
