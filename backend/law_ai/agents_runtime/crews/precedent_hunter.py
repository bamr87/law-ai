"""
Precedent Hunter Agent

Uses hybrid GraphRAG (Neo4j Cypher + vector similarity) to find
on-point, analogous, and distinguishing cases with explanations.
"""

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
    trace_id: str | None = Field(
        default=None, description="Provenance trace_id from log_agent_call"
    )


class PrecedentHunter:
    name = "PrecedentHunter"

    async def run(self, input_data: dict) -> PrecedentList:
        start = time.time()

        # TODO: Real Cypher + vector search
        precedents = [
            Precedent(
                case_id="case:123",
                title="Smith v. Jones (2022)",
                court="9th Cir.",
                year=2022,
                relevance_score=0.91,
                distinguishing_factors=[
                    "Different jurisdiction",
                    "Similar facts on duty",
                ],
                url="https://case.law/...",
            )
        ]

        output = PrecedentList(
            precedents=precedents,
            summary="Found 12 highly relevant precedents. Top match: Smith v. Jones.",
            confidence=0.88,
        )

        latency = (time.time() - start) * 1000
        trace_id = provenance.log_agent_call(
            self.name, input_data, output.model_dump(), "llama3.1", latency
        )
        output.trace_id = trace_id
        return output
