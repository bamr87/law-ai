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
    _call_ollama,
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
# _call_ollama error path
# ---------------------------------------------------------------------------


class TestCallOllama:
    def test_raises_on_url_error(self) -> None:
        import urllib.error

        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")),
            pytest.raises(RuntimeError, match="Ollama unreachable"),
        ):
            _call_ollama("prompt", model="llama3", base_url="http://localhost:11434")


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
                ollama_caller=lambda *_, **__: _FAKE_TARGETS,
            )
        assert state["targets"][0]["query"] == "Brown v. Board"
        assert any(e["type"] == "topic_frontier.prioritize" for e in recorded)

    @pytest.mark.asyncio
    async def test_empty_targets_on_llm_failure(self) -> None:
        def _fail(*args: Any, **kwargs: Any) -> str:
            raise RuntimeError("Ollama down")

        state = await _node_prioritize(
            {"trace_id": "x", "orphan_citations": [], "under_cited_jurisdictions": []},
            ollama_caller=lambda *_, **__: "bad json",
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
                ollama_caller=lambda *_, **__: _FAKE_TARGETS,
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
                ollama_caller=lambda *_, **__: "[]",
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
