"""LangGraph workflows (spec 010).

Stateful, resumable agent workflows that complement the CrewAI crews under
``app.agents.crews``. Every node is wrapped by ``app.core.provenance.logged_node``
so each LLM call shows up in both the local audit store and Arize Phoenix
when telemetry is enabled.

Imports here stay top-level *only* for cheap symbols. The heavy
``langgraph`` / ``langchain-ollama`` machinery is loaded lazily inside
``runtime.build_checkpointer`` and ``legal_workflow.LegalWorkflow`` so a
default ``pip install -e ".[dev]"`` (no ``local-ai`` extra) keeps booting.
"""

from __future__ import annotations

__all__ = ["LegalWorkflow", "LegalWorkflowOutput", "build_checkpointer"]


def __getattr__(name: str):  # pragma: no cover - thin re-export shim
    if name == "build_checkpointer":
        from law_ai.agents_runtime.graphs.runtime import build_checkpointer

        return build_checkpointer
    if name in {"LegalWorkflow", "LegalWorkflowOutput"}:
        from law_ai.agents_runtime.graphs import legal_workflow

        return getattr(legal_workflow, name)
    raise AttributeError(name)
