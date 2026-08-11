"""
Precedent Hunter Agent

Will use hybrid GraphRAG (Neo4j Cypher + vector similarity) to find
on-point, analogous, and distinguishing cases with explanations.

Until real retrieval lands (BL-20260502-04), this agent is HONEST about
being unimplemented: it returns zero precedents at confidence 0.0 with
``degraded=True`` so callers force human review, instead of fabricating
case law (constitution §4 provenance + §13 attribution). It must never
invent precedents or log them under a real model name.
"""

from typing import Any

from pydantic import BaseModel, Field
import time
from law_ai.core.provenance import provenance


class Precedent(BaseModel):
    case_id: str
    title: str
    court: str
    year: int
    relevance_score: float
    distinguishing_factors: list[str] = Field(default_factory=list)
    url: str


class PrecedentList(BaseModel):
    precedents: list[Precedent]
    summary: str
    confidence: float
    degraded: bool = Field(
        default=False,
        description=(
            "True when no real retrieval ran (unimplemented/offline path). "
            "Degraded output must never be presented as genuine search results."
        ),
    )
    trace_id: str | None = Field(
        default=None, description="Provenance trace_id from log_agent_call"
    )


class PrecedentHunter:
    name = "PrecedentHunter"

    async def run(self, input_data: dict[str, Any]) -> PrecedentList:
        start = time.time()

        # Real Cypher + vector search is not implemented yet. Report exactly
        # that — "no results in our corpus" must never read as "no such law",
        # and fabricated results must never read as retrieval (§13).
        output = PrecedentList(
            precedents=[],
            summary=(
                "Precedent search is not yet implemented: no graph or vector "
                "retrieval was performed. 0 precedents retrieved. Absence of "
                "results here does NOT mean no relevant precedent exists."
            ),
            confidence=0.0,
            degraded=True,
        )

        latency = (time.time() - start) * 1000
        trace_id = provenance.log_agent_call(
            self.name,
            input_data,
            output.model_dump(),
            "degraded/not-implemented",
            latency,
            confidence=output.confidence,
        )
        output.trace_id = trace_id
        return output
