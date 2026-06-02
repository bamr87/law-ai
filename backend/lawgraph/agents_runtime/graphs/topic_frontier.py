"""TopicFrontier — 4-node sequential workflow (spec 018 T-007).

Nodes:

    scan_graph → prioritize → dispatch → summarize

Note: Despite the module name referring to "LangGraph", this workflow uses
direct sequential async execution (``await _node_*(state)``) rather than a
``langgraph.graph.StateGraph`` with compiled edges.  A future spec will
migrate to a proper StateGraph to gain retries, conditional branching, and
checkpointing (tracked as a BACKLOG follow-up).

``scan_graph``   reads two Cypher helpers (``list_orphan_citations``,
                 ``list_under_cited_jurisdictions``) and populates the
                 state with gap data.

``prioritize``   calls Ollama with the versioned prompt template and
                 returns up to 3 ranked fetch targets.

``dispatch``     iterates the targets, calls ``SOURCE_REGISTRY[name].fetch``
                 for each, then routes every :class:`RawDoc` through
                 ``IngestionScout.run_and_commit``.  **Never** writes Neo4j
                 directly (constitution §12 invariant I1).

``summarize``    logs the full cycle summary via ``core.provenance`` and
                 returns a :class:`TopicFrontierOutput`.

Design notes:
- Every LLM call is logged; every Neo4j write goes through
  ``IngestionScout.run_and_commit`` (which carries ``agent_version``).
- ``human_approval_required`` is set on any adapter whose
  ``requires_human_approval`` flag is True.
- Provider/model selection via ``lawgraph.core.config`` only.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from lawgraph.core import audit_jsonl
from lawgraph.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("lawgraph.graphs.topic_frontier")

AGENT_VERSION = "lawgraph.agents_runtime.graphs.topic_frontier.v1"
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


def _call_ollama(prompt: str, *, model: str, base_url: str, timeout: int = 120) -> str:
    """Call Ollama ``/api/generate`` and return the raw text response.

    Raises :class:`RuntimeError` on network failure so callers can fall back
    gracefully.
    """
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            return str(body.get("response", ""))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {base_url}: {exc}") from exc


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
        docs = list(adapter.fetch(query, limit=5))
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
        from lawgraph.core.neo4j.driver import get_neo4j_driver
        from lawgraph.core.neo4j import queries as neo4j_queries

        driver = get_neo4j_driver()
        async with driver.session() as session:
            orphans = await neo4j_queries.list_orphan_citations(session, limit=20)
            under = await neo4j_queries.list_under_cited_jurisdictions(
                session, limit=10
            )
    else:
        async with neo4j_session_factory() as session:
            from lawgraph.core.neo4j import queries as neo4j_queries

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
    ollama_caller: Any = None,
) -> TopicFrontierState:
    """Call Ollama to rank fetch targets; injectable for tests."""
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

    if ollama_caller is not None:
        raw = ollama_caller(full_prompt, model=model, base_url=base_url)
    else:
        raw = _call_ollama(full_prompt, model=model, base_url=base_url)

    targets = _parse_targets(raw)

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
        from lawgraph.ingestionapp.sources import SOURCE_REGISTRY

        registry = SOURCE_REGISTRY  # type: ignore[assignment]

    if scout_factory is None:
        from lawgraph.ingestionapp.services.scout import IngestionScout

        scout_factory = IngestionScout  # type: ignore[assignment]

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

        scout = scout_factory()
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
    :param ollama_caller: callable with signature
        ``(prompt, *, model, base_url) -> str``.  ``None`` → real Ollama.
    :param registry: source adapter dict override.  ``None`` → ``SOURCE_REGISTRY``.
    :param scout_factory: callable that returns an ``IngestionScout``.
    """

    human_approval_required: bool = False

    def __init__(
        self,
        *,
        neo4j_session_factory: Any = None,
        ollama_caller: Any = None,
        registry: dict[str, Any] | None = None,
        scout_factory: Any = None,
    ) -> None:
        self._neo4j_session_factory = neo4j_session_factory
        self._ollama_caller = ollama_caller
        self._registry = registry
        self._scout_factory = scout_factory

    async def run(self, *, trace_id: str | None = None) -> TopicFrontierOutput:
        """Execute all 4 nodes in sequence and return :class:`TopicFrontierOutput`.

        Example::

            tf = TopicFrontier(ollama_caller=mock_llm, ...)
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

        state = await _node_scan_graph(
            state, neo4j_session_factory=self._neo4j_session_factory
        )
        state = await _node_prioritize(state, ollama_caller=self._ollama_caller)
        state = await _node_dispatch(
            state, registry=self._registry, scout_factory=self._scout_factory
        )
        state = await _node_summarize(state)

        latency_ms = (time.monotonic() - t0) * 1000.0
        return TopicFrontierOutput(
            trace_id=trace_id,
            targets=[FetchTarget(**t) for t in state.get("targets", [])],
            dispatched=[DispatchResult(**d) for d in state.get("dispatched", [])],
            latency_ms=latency_ms,
            human_approval_required=state.get("human_approval_required", False),
        )
