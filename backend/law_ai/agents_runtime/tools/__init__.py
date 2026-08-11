"""Agent tools (AGENTS.md canonical layout).

Tools are the capabilities agents call out to: graph retrieval, citation
resolution, external source clients. Every tool logs through
``law_ai.core.provenance`` (constitution §4) and returns plain
dicts/Pydantic models — no driver objects leak to callers.
"""

from law_ai.agents_runtime.tools.graph_rag import (
    GraphRAGRetriever,
    RetrievalCoverage,
    build_default_retriever,
)

__all__ = ["GraphRAGRetriever", "RetrievalCoverage", "build_default_retriever"]
