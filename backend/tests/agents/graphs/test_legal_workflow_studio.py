"""The module-level graph factory a LangGraph host loads (BL-20260502-01).

`langchain/langgraph-api` (compose profile `studio`) imports
`law_ai.agents_runtime.graphs.studio:make_graph` and serves whatever it
returns. These tests pin the contract that entry point depends on: a
module-level factory exists, it compiles the same three nodes the API runs,
and it hands back a graph with no checkpointer attached (the server injects
its own and rejects one that arrives pre-bound).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "langgraph",
    reason="langgraph not installed (add the local-ai extra)",
)

from law_ai.agents_runtime.graphs.legal_workflow import (
    LegalWorkflow,
    build_legal_workflow_graph,
)
from law_ai.agents_runtime.graphs.studio import make_graph

BACKEND_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_NODES = {"retrieve", "analyze", "cite_check"}


def _node_names(graph: object) -> set[str]:
    return {
        name for name in graph.get_graph().nodes if name not in {"__start__", "__end__"}
    }


def test_factory_compiles_the_three_nodes() -> None:
    graph = build_legal_workflow_graph()
    assert _node_names(graph) >= EXPECTED_NODES


def test_factory_without_checkpointer_leaves_persistence_to_the_host() -> None:
    graph = build_legal_workflow_graph()
    assert getattr(graph, "checkpointer", None) in (None, False)


def test_factory_accepts_an_explicit_checkpointer() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    saver = InMemorySaver()
    graph = build_legal_workflow_graph(checkpointer=saver)
    assert graph.checkpointer is saver


def test_workflow_builds_its_graph_through_the_same_factory() -> None:
    """No drift: Studio must serve the graph the API actually runs."""
    workflow = LegalWorkflow()
    assert _node_names(workflow._build_graph(None)) == _node_names(
        build_legal_workflow_graph()
    )


def test_factory_binds_the_supplied_workflow_instance() -> None:
    workflow = LegalWorkflow()
    graph = build_legal_workflow_graph(workflow=workflow)
    retrieve = graph.get_graph().nodes["retrieve"]
    assert _node_names(graph) >= EXPECTED_NODES
    assert retrieve is not None


def test_studio_entry_point_returns_a_compiled_graph() -> None:
    graph = make_graph()
    assert _node_names(graph) >= EXPECTED_NODES
    assert getattr(graph, "checkpointer", None) in (None, False)


def test_langgraph_json_points_at_the_studio_entry_point() -> None:
    config = json.loads((BACKEND_ROOT / "langgraph.json").read_text())
    graphs = config["graphs"]
    assert graphs, "langgraph.json declares no graphs"
    spec = graphs["legal_workflow"]
    rel, _, attr = spec.partition(":")
    assert attr == "make_graph"
    assert (BACKEND_ROOT / rel).is_file(), f"langgraph.json points at a missing {rel}"
