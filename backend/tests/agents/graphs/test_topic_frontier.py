"""Unit tests for TopicFrontier LangGraph workflow (spec 018 T-007).

All tests use injected fakes — no Ollama, Neo4j, or IngestionScout required.
Run via:  make test-backend  (docker compose run --rm --no-deps backend pytest ...)
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

import law_ai.agents_runtime.graphs.topic_frontier as tf_module
from law_ai.agents_runtime.graphs.topic_frontier import (
    TopicFrontier,
    TopicFrontierOutput,
    _node_prioritize,
    _node_scan_graph,
    _node_dispatch,
    _node_summarize,
    _dispatch_target,
    _parse_targets,
    _call_llm,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FAKE_TARGETS = json.dumps(
    [
        {
            "query": "Brown v. Board",
            "jurisdiction": "us",
            "reason": "landmark",
            "priority": 1,
        }
    ]
)

_LLM_OUTPUT_FENCED = f"```json\n{_FAKE_TARGETS}\n```"


def _make_fake_session(orphans: list[str], under: list[str]) -> Any:
    """Return an async context-manager that yields a mock session."""

    @asynccontextmanager
    async def _factory() -> Any:
        session = AsyncMock()
        yield session

    return _factory


# ---------------------------------------------------------------------------
# _parse_targets
# ---------------------------------------------------------------------------


class TestParseTargets:
    def test_valid_array(self) -> None:
        out = _parse_targets(_FAKE_TARGETS)
        assert len(out) == 1
        assert out[0]["query"] == "Brown v. Board"

    def test_fenced_markdown(self) -> None:
        out = _parse_targets(_LLM_OUTPUT_FENCED)
        assert len(out) == 1

    def test_empty_on_bad_json(self) -> None:
        assert _parse_targets("not json at all") == []

    def test_caps_at_three(self) -> None:
        big = json.dumps([{"query": f"q{i}", "priority": i} for i in range(10)])
        assert len(_parse_targets(big)) == 3

    def test_empty_array(self) -> None:
        assert _parse_targets("[]") == []


# ---------------------------------------------------------------------------
# _call_llm error path
# ---------------------------------------------------------------------------


class TestCallLLM:
    def test_raises_when_whole_chain_fails(self) -> None:
        """The chain-backed transport preserves the RuntimeError contract."""
        with (
            patch(
                "law_ai.core.llm.generate",
                side_effect=OSError("down"),
            ),
            pytest.raises(RuntimeError, match="no LLM provider"),
        ):
            _call_llm("prompt", model="llama3", base_url="http://localhost:11434")


# ---------------------------------------------------------------------------
# _node_scan_graph — injected session factory
# ---------------------------------------------------------------------------


class TestNodeScanGraph:
    @pytest.mark.asyncio
    async def test_populates_state(self) -> None:
        orphans = ["123 U.S. 456"]
        under = ["us-co"]

        from law_ai.core.neo4j import queries as q

        q.list_orphan_citations = AsyncMock(return_value=orphans)
        q.list_under_cited_jurisdictions = AsyncMock(return_value=under)

        @asynccontextmanager
        async def _fake_session() -> Any:
            yield MagicMock()

        state2 = await _node_scan_graph(
            {"trace_id": "t1"}, neo4j_session_factory=_fake_session
        )
        assert state2.get("orphan_citations") == orphans


# ---------------------------------------------------------------------------
# _node_prioritize — injected LLM caller
# ---------------------------------------------------------------------------


class TestDefaultCallerInsideEventLoop:
    """The node runs in the event loop, so its default caller must be async.

    Regression guard: every other node test injects ``llm_caller``, so a
    default path that blocks (or refuses to run) inside a running loop would
    otherwise only surface in production.
    """

    @pytest.mark.asyncio
    async def test_default_path_awaits_the_chain(self, tmp_path: Any) -> None:
        from law_ai.core.llm.base import LLMResult

        result = LLMResult(
            text=_FAKE_TARGETS,
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )
        with (
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch(
                "law_ai.core.llm.agenerate",
                new=AsyncMock(return_value=result),
            ) as mock_agen,
        ):
            state = await _node_prioritize(
                {
                    "trace_id": "abc",
                    "orphan_citations": ["123 U.S. 1"],
                    "under_cited_jurisdictions": ["us-co"],
                },
            )
        assert mock_agen.await_count == 1
        assert state["targets"][0]["query"] == "Brown v. Board"


class TestNodePrioritize:
    @pytest.mark.asyncio
    async def test_calls_ollama_and_parses(self, tmp_path: Any) -> None:
        recorded: list[dict] = []
        with patch.object(tf_module.audit_jsonl, "record", recorded.append):
            state = await _node_prioritize(
                {
                    "trace_id": "abc",
                    "orphan_citations": ["123 U.S. 1"],
                    "under_cited_jurisdictions": ["us-co"],
                },
                llm_caller=lambda *_, **__: _FAKE_TARGETS,
            )
        assert state["targets"][0]["query"] == "Brown v. Board"
        assert any(e["type"] == "topic_frontier.prioritize" for e in recorded)

    @pytest.mark.asyncio
    async def test_empty_targets_on_llm_failure(self) -> None:
        def _fail(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("Ollama down")

        state = await _node_prioritize(
            {"trace_id": "x", "orphan_citations": [], "under_cited_jurisdictions": []},
            llm_caller=lambda *_, **__: "bad json",
        )
        assert state["targets"] == []


# ---------------------------------------------------------------------------
# _node_dispatch — injected registry + scout
# ---------------------------------------------------------------------------


class TestNodeDispatch:
    def _make_adapter(self, name: str, jurisdiction: str = "*") -> MagicMock:
        adapter = MagicMock()
        adapter.name = name
        adapter.jurisdiction = jurisdiction
        adapter.requires_human_approval = False
        doc = MagicMock()
        doc.source_name = name
        doc.source_url = f"https://example.com/{name}/1"
        doc.title = "Fake Case"
        doc.text = "full text"
        adapter.fetch.return_value = [doc]
        return adapter

    @pytest.mark.asyncio
    async def test_dispatches_through_scout(self, settings) -> None:
        adapter = self._make_adapter("courtlistener")
        scout = AsyncMock()
        scout.run_and_commit = AsyncMock(
            return_value={"committed": True, "confidence": 0.9}
        )

        with patch.object(
            tf_module.settings,
            "AUTONOMY_ALLOWED_SOURCES",
            ["courtlistener"],
            create=True,
        ):
            state = await _node_dispatch(
                {
                    "trace_id": "t",
                    "targets": [{"query": "q", "jurisdiction": "*", "priority": 1}],
                },
                registry={"courtlistener": adapter},
                scout_factory=MagicMock(return_value=scout),
            )
        assert state["dispatched"][0]["committed"] is True

    @pytest.mark.asyncio
    async def test_skip_adapter_not_in_allowlist(self, settings) -> None:
        adapter = self._make_adapter("courtlistener")
        with patch.object(
            tf_module.settings, "AUTONOMY_ALLOWED_SOURCES", [], create=True
        ):
            state = await _node_dispatch(
                {
                    "trace_id": "t",
                    "targets": [{"query": "q", "jurisdiction": "*", "priority": 1}],
                },
                registry={"courtlistener": adapter},
                scout_factory=MagicMock(return_value=AsyncMock()),
            )
        assert state["dispatched"] == []

    @pytest.mark.asyncio
    async def test_sets_human_approval_when_adapter_requires_it(self, settings) -> None:
        # FR-3 / AC-1: a quarantined doc is not committed, and the dispatch
        # chain must hand force_quarantine=True down to run_and_commit.
        adapter = self._make_adapter("courtlistener")
        adapter.requires_human_approval = True
        scout = AsyncMock()
        scout.run_and_commit = AsyncMock(
            return_value={"committed": False, "pending": True, "confidence": 0.9}
        )
        with patch.object(
            tf_module.settings,
            "AUTONOMY_ALLOWED_SOURCES",
            ["courtlistener"],
            create=True,
        ):
            state = await _node_dispatch(
                {
                    "trace_id": "t",
                    "targets": [{"query": "q", "jurisdiction": "*", "priority": 1}],
                },
                registry={"courtlistener": adapter},
                scout_factory=MagicMock(return_value=scout),
            )
        assert state["human_approval_required"] is True
        scout.run_and_commit.assert_called_once_with(ANY, force_quarantine=True)

    @pytest.mark.asyncio
    async def test_force_quarantine_passed_when_adapter_requires_approval(
        self, settings
    ) -> None:
        """BL-20260511-30: run_and_commit receives force_quarantine=True."""
        adapter = self._make_adapter("courtlistener")
        adapter.requires_human_approval = True
        scout = AsyncMock()
        scout.run_and_commit = AsyncMock(
            return_value={"committed": False, "confidence": 0.95, "pending": True}
        )
        with patch.object(
            tf_module.settings,
            "AUTONOMY_ALLOWED_SOURCES",
            ["courtlistener"],
            create=True,
        ):
            await _node_dispatch(
                {
                    "trace_id": "t",
                    "targets": [{"query": "q", "jurisdiction": "*", "priority": 1}],
                },
                registry={"courtlistener": adapter},
                scout_factory=MagicMock(return_value=scout),
            )
        # Verify force_quarantine=True was passed to run_and_commit
        scout.run_and_commit.assert_called_once()
        _, kwargs = scout.run_and_commit.call_args
        assert kwargs["force_quarantine"] is True

    @pytest.mark.asyncio
    async def test_dispatch_summary_shows_not_committed_when_force_quarantine(
        self,
    ) -> None:
        """FR-2 / AC-2: a force-quarantined doc surfaces committed=False in the
        dispatch summary, even though run_and_commit succeeded."""
        adapter = self._make_adapter("courtlistener")
        scout = AsyncMock()
        scout.run_and_commit = AsyncMock(
            return_value={"committed": False, "pending": True, "confidence": 0.5}
        )

        dispatched = await _dispatch_target(
            scout,
            adapter,
            "q",
            [],
            force_quarantine=True,
        )

        assert len(dispatched) == 1
        entry = dispatched[0]
        assert entry["committed"] is False
        assert entry["confidence"] == 0.5
        _, kwargs = scout.run_and_commit.call_args
        assert kwargs["force_quarantine"] is True


# ---------------------------------------------------------------------------
# _node_summarize — logs provenance
# ---------------------------------------------------------------------------


class TestNodeSummarize:
    @pytest.mark.asyncio
    async def test_records_audit_event(self) -> None:
        recorded: list[dict] = []
        with patch.object(tf_module.audit_jsonl, "record", recorded.append):
            await _node_summarize(
                {
                    "trace_id": "z",
                    "targets": [],
                    "dispatched": [],
                    "human_approval_required": False,
                }
            )
        assert any(e["type"] == "topic_frontier.summarize" for e in recorded)


# ---------------------------------------------------------------------------
# TopicFrontier.run — end-to-end with all fakes
# ---------------------------------------------------------------------------


class TestTopicFrontierRun:
    @pytest.mark.asyncio
    async def test_returns_output_model(self, settings) -> None:
        adapter = MagicMock()
        adapter.name = "courtlistener"
        adapter.jurisdiction = "*"
        adapter.requires_human_approval = False
        doc = MagicMock()
        doc.source_name = "courtlistener"
        doc.source_url = "https://example.com/1"
        doc.title = "Case"
        doc.text = "text"
        adapter.fetch.return_value = [doc]

        scout = AsyncMock()
        scout.run_and_commit = AsyncMock(
            return_value={"committed": True, "confidence": 0.95}
        )

        from law_ai.core.neo4j import queries as neo4j_q

        with (
            patch.object(
                neo4j_q, "list_orphan_citations", AsyncMock(return_value=["1 U.S. 1"])
            ),
            patch.object(
                neo4j_q,
                "list_under_cited_jurisdictions",
                AsyncMock(return_value=["us-co"]),
            ),
            patch.object(
                tf_module.settings,
                "AUTONOMY_ALLOWED_SOURCES",
                ["courtlistener"],
                create=True,
            ),
            patch.object(tf_module.audit_jsonl, "record", MagicMock()),
        ):

            @asynccontextmanager
            async def _fake_session() -> Any:
                yield MagicMock()

            tf = TopicFrontier(
                neo4j_session_factory=_fake_session,
                llm_caller=lambda *_, **__: _FAKE_TARGETS,
                registry={"courtlistener": adapter},
                scout_factory=MagicMock(return_value=scout),
            )
            output = await tf.run(trace_id="test-trace")

        assert isinstance(output, TopicFrontierOutput)
        assert output.trace_id == "test-trace"
        assert output.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_empty_graph_no_crash(self) -> None:
        """Zero orphans + zero under-cited jurisdictions → empty output, no error."""
        from law_ai.core.neo4j import queries as neo4j_q

        with (
            patch.object(neo4j_q, "list_orphan_citations", AsyncMock(return_value=[])),
            patch.object(
                neo4j_q,
                "list_under_cited_jurisdictions",
                AsyncMock(return_value=[]),
            ),
            patch.object(tf_module.audit_jsonl, "record", MagicMock()),
        ):

            @asynccontextmanager
            async def _fake_session2() -> Any:
                yield MagicMock()

            tf = TopicFrontier(
                neo4j_session_factory=_fake_session2,
                llm_caller=lambda *_, **__: "[]",
                registry={},
                scout_factory=MagicMock(return_value=AsyncMock()),
            )
            output = await tf.run()

        assert output.targets == []
        assert output.dispatched == []


# ---------------------------------------------------------------------------
# HITL invariant
# ---------------------------------------------------------------------------


class TestHumanApprovalDefault:
    def test_default_false(self) -> None:
        tf = TopicFrontier()
        assert tf.human_approval_required is False


# ---------------------------------------------------------------------------
# FR-4 / AC-3 — integration: a requires_human_approval adapter produces a
# PendingReview row (not a Neo4j Case) through the full dispatch chain.
#
# Requires the Docker stack (postgres) + CELERY_TASK_ALWAYS_EAGER. Excluded
# from `make test-backend` (which drops the `integration` marker). Mirrors the
# sync-test-body pattern from tests/ingestion/test_scout_integration.py and
# BL-20260510-01 to avoid SynchronousOnlyOperation in an async context.
#
# NOTE: spec FR-4 step 3 says to assert on PendingReview.source == source_url,
# but scout's OpinionExtractor hardcodes source="courtlistener" and stores the
# doc URL as the row's primary key (id). We therefore look the row up by pk.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_requires_human_approval_produces_pending_review_row(
    settings, monkeypatch
) -> None:
    from asgiref.sync import async_to_sync

    from law_ai.ingestionapp.models import PendingReview

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    # Eager Celery executes the quarantine task's synchronous Django ORM writes
    # inline — here, inside the async_to_sync event loop below — which Django
    # rejects with SynchronousOnlyOperation, so the scout silently falls back to
    # JSONL and no PendingReview row is written (BL-20260510-01). In production
    # the task runs in a separate worker process (no running loop), so this
    # guard only bites in eager tests; allow sync ORM for this controlled run.
    monkeypatch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

    source_url = "https://example.com/hitl/quarantine-me"
    adapter = MagicMock()
    adapter.name = "courtlistener"
    adapter.jurisdiction = "*"
    adapter.requires_human_approval = True
    doc = MagicMock()
    doc.source_name = "courtlistener"
    doc.source_url = source_url
    doc.title = "Forced HITL Case"
    doc.text = "full opinion text"
    adapter.fetch.return_value = [doc]

    with patch.object(
        tf_module.settings,
        "AUTONOMY_ALLOWED_SOURCES",
        ["courtlistener"],
        create=True,
    ):
        state = async_to_sync(_node_dispatch)(
            {
                "trace_id": "t-hitl",
                "targets": [{"query": "q", "jurisdiction": "*", "priority": 1}],
            },
            registry={"courtlistener": adapter},
        )

    assert state["human_approval_required"] is True
    assert state["dispatched"][0]["committed"] is False
    assert PendingReview.objects.filter(pk=source_url).exists()


# ---------------------------------------------------------------------------
# Spec 027: real LangGraph StateGraph compilation
# ---------------------------------------------------------------------------


class TestStateGraphCompilation:
    def test_build_graph_compiles_all_four_nodes(self) -> None:
        pytest.importorskip("langgraph")
        tf = tf_module.TopicFrontier()
        graph = tf._build_graph()
        node_names = set(graph.get_graph().nodes)
        assert {"scan_graph", "prioritize", "dispatch", "summarize"} <= node_names

    @pytest.mark.asyncio
    async def test_run_executes_through_compiled_graph(self) -> None:
        """run() routes through graph.ainvoke when langgraph is installed."""
        pytest.importorskip("langgraph")

        with (
            patch.object(
                tf_module,
                "_node_scan_graph",
                new=AsyncMock(
                    side_effect=lambda state, **_: {
                        **state,
                        "orphan_citations": [],
                        "under_cited_jurisdictions": [],
                    }
                ),
            ),
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch.object(tf_module.provenance, "log_agent_call", lambda *a, **k: "t"),
        ):
            tf = tf_module.TopicFrontier(
                llm_caller=lambda *_, **__: "[]",
                registry={},
                scout_factory=MagicMock,
            )
            out = await tf.run(trace_id="t-graph")
        assert out.trace_id == "t-graph"
        assert out.targets == []


# ---------------------------------------------------------------------------
# BL-20260511-21: state-machine transition assertions
# BL-20260511-31: checkpointing, retries, conditional branching
# ---------------------------------------------------------------------------


def _stub_scan(state: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {
        **state,
        "orphan_citations": ["410 U.S. 113"],
        "under_cited_jurisdictions": ["us-ca"],
    }


class _RecordingScout:
    """IngestionScout stand-in that commits everything it is handed."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def run_and_commit(self, doc: Any) -> Any:
        self.calls.append(doc)
        return MagicMock(committed=True, confidence=0.9, human_approval_required=False)


class TestGraphTransitions:
    """The compiled graph's *edges*, not just its nodes (BL-20260511-21)."""

    def _edges(self, tf: Any) -> set[tuple[str, str]]:
        graph = tf._build_graph().get_graph()
        return {(e.source, e.target) for e in graph.edges}

    def test_edge_set_matches_the_declared_state_machine(self) -> None:
        pytest.importorskip("langgraph")
        edges = self._edges(tf_module.TopicFrontier())
        assert edges == {
            ("__start__", "scan_graph"),
            ("scan_graph", "prioritize"),
            ("prioritize", "dispatch"),
            ("prioritize", "summarize"),
            ("dispatch", "summarize"),
            ("summarize", "__end__"),
        }

    def test_prioritize_branch_is_conditional(self) -> None:
        """The two prioritize edges are a branch, not two unconditional edges."""
        pytest.importorskip("langgraph")
        graph = tf_module.TopicFrontier()._build_graph().get_graph()
        out_of_prioritize = [e for e in graph.edges if e.source == "prioritize"]
        assert len(out_of_prioritize) == 2
        assert all(e.conditional for e in out_of_prioritize)
        # dispatch -> summarize stays a plain edge
        assert not [
            e
            for e in graph.edges
            if e.source == "dispatch" and e.target == "summarize" and e.conditional
        ]

    def test_route_after_prioritize(self) -> None:
        assert tf_module._route_after_prioritize({"targets": [{"query": "x"}]}) == (
            "dispatch"
        )
        assert tf_module._route_after_prioritize({"targets": []}) == "summarize"
        assert tf_module._route_after_prioritize({}) == "summarize"

    def test_retry_policy_on_the_network_bound_nodes(self) -> None:
        """prioritize/dispatch retry; scan_graph/summarize do not."""
        pytest.importorskip("langgraph")
        compiled = tf_module.TopicFrontier()._build_graph()
        nodes = compiled.nodes
        assert nodes["prioritize"].retry_policy
        assert nodes["dispatch"].retry_policy
        assert not nodes["scan_graph"].retry_policy
        assert not nodes["summarize"].retry_policy

    @pytest.mark.asyncio
    async def test_nodes_execute_in_declared_order(self) -> None:
        """astream(updates) proves the traversal, not just the final output."""
        pytest.importorskip("langgraph")
        scout = _RecordingScout()
        adapter = MagicMock()
        adapter.requires_human_approval = False
        adapter.fetch = MagicMock(
            return_value=[MagicMock(source_url="https://x/1", source_name="cl")]
        )

        with (
            patch.object(
                tf_module, "_node_scan_graph", new=AsyncMock(side_effect=_stub_scan)
            ),
            patch.object(
                tf_module,
                "_node_dispatch",
                new=AsyncMock(
                    side_effect=lambda state, **_: {**state, "dispatched": []}
                ),
            ),
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch.object(tf_module.provenance, "log_agent_call", lambda *a, **k: "t"),
        ):
            tf = tf_module.TopicFrontier(
                llm_caller=lambda *_, **__: _FAKE_TARGETS,
                registry={"courtlistener": adapter},
                scout_factory=lambda: scout,
            )
            graph = tf._build_graph()
            seen: list[str] = []
            async for chunk in graph.astream(
                {
                    "trace_id": "t-order",
                    "orphan_citations": [],
                    "under_cited_jurisdictions": [],
                    "targets": [],
                    "dispatched": [],
                    "human_approval_required": False,
                    "latency_ms": 0.0,
                },
                stream_mode="updates",
            ):
                seen.extend(chunk.keys())

        assert seen == ["scan_graph", "prioritize", "dispatch", "summarize"]

    @pytest.mark.asyncio
    async def test_empty_ranking_skips_dispatch(self) -> None:
        """The conditional edge means dispatch never runs on an empty ranking."""
        pytest.importorskip("langgraph")

        with (
            patch.object(
                tf_module, "_node_scan_graph", new=AsyncMock(side_effect=_stub_scan)
            ),
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch.object(tf_module.provenance, "log_agent_call", lambda *a, **k: "t"),
        ):
            tf = tf_module.TopicFrontier(
                llm_caller=lambda *_, **__: "[]",
                registry={},
                scout_factory=MagicMock,
            )
            graph = tf._build_graph()
            seen: list[str] = []
            async for chunk in graph.astream(
                {
                    "trace_id": "t-empty",
                    "orphan_citations": [],
                    "under_cited_jurisdictions": [],
                    "targets": [],
                    "dispatched": [],
                    "human_approval_required": False,
                    "latency_ms": 0.0,
                },
                stream_mode="updates",
            ):
                seen.extend(chunk.keys())

        assert seen == ["scan_graph", "prioritize", "summarize"]
        assert "dispatch" not in seen

    @pytest.mark.asyncio
    async def test_sequential_fallback_honours_the_same_branch(self) -> None:
        """_run_sequential must not drift from the compiled graph."""
        dispatch = AsyncMock(side_effect=lambda state, **_: {**state, "dispatched": []})
        with (
            patch.object(
                tf_module, "_node_scan_graph", new=AsyncMock(side_effect=_stub_scan)
            ),
            patch.object(tf_module, "_node_dispatch", new=dispatch),
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch.object(tf_module.provenance, "log_agent_call", lambda *a, **k: "t"),
        ):
            tf = tf_module.TopicFrontier(
                llm_caller=lambda *_, **__: "[]", registry={}, scout_factory=MagicMock
            )
            await tf._run_sequential(
                {
                    "trace_id": "t-seq",
                    "orphan_citations": [],
                    "under_cited_jurisdictions": [],
                    "targets": [],
                    "dispatched": [],
                    "human_approval_required": False,
                    "latency_ms": 0.0,
                }
            )
        dispatch.assert_not_awaited()


class TestCheckpointing:
    """BL-20260511-31: the compiled graph persists node state when asked."""

    @pytest.mark.asyncio
    async def test_run_writes_checkpoints_for_the_thread(self) -> None:
        pytest.importorskip("langgraph")
        from langgraph.checkpoint.memory import MemorySaver

        saver = MemorySaver()
        with (
            patch.object(
                tf_module, "_node_scan_graph", new=AsyncMock(side_effect=_stub_scan)
            ),
            patch.object(tf_module.audit_jsonl, "record", lambda *_: None),
            patch.object(tf_module.provenance, "log_agent_call", lambda *a, **k: "t"),
        ):
            tf = tf_module.TopicFrontier(
                llm_caller=lambda *_, **__: "[]",
                registry={},
                scout_factory=MagicMock,
                checkpointer=saver,
            )
            out = await tf.run(trace_id="t-ckpt", thread_id="thread-1")

        assert out.trace_id == "t-ckpt"
        config = {"configurable": {"thread_id": "thread-1"}}
        tuples = [c async for c in saver.alist(config)]
        assert tuples, "expected checkpoints recorded under thread-1"
        latest = await saver.aget(config)
        assert latest is not None
        assert latest["channel_values"]["orphan_citations"] == ["410 U.S. 113"]

    @pytest.mark.asyncio
    async def test_no_checkpointer_means_no_config(self) -> None:
        """Default construction still compiles without persistence."""
        pytest.importorskip("langgraph")
        tf = tf_module.TopicFrontier()
        assert tf._checkpointer is None
        compiled = tf._build_graph()
        assert compiled.checkpointer is None
