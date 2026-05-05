"""
Legal Analyst Agent

Produces structured IRAC briefs, issue spotting, argument mapping,
and risk assessment using GraphRAG retrieval + LLM reasoning.

Spec 010 FR-3 / T-006: when ``input_data["use_langgraph"]`` is truthy,
delegate to :class:`app.agents.graphs.LegalWorkflow` so the response is
backed by a real Ollama call + provenance trace. Default behavior is
unchanged for back-compat with existing tests and the Analysis Studio.
"""

from pydantic import BaseModel, Field
from lawgraph.core.provenance import provenance
import time


class IRACOutput(BaseModel):
    issue: str = Field(..., description="Key legal issue identified")
    rule: str = Field(..., description="Applicable legal rules / black letter law")
    application: str = Field(..., description="Application of rules to facts")
    conclusion: str = Field(..., description="Conclusion and recommended action")
    sources: list[dict] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning_trace: list[str] = Field(default_factory=list)
    trace_id: str | None = Field(
        default=None, description="Provenance trace_id from log_agent_call"
    )
    phoenix_trace_url: str | None = Field(
        default=None,
        description="Deep-link to the Phoenix span tree (spec 010 FR-3).",
    )
    langgraph_thread_id: str | None = Field(
        default=None,
        description="LangGraph checkpoint thread id; resume with the same id.",
    )


class LegalAnalyst:
    name = "LegalAnalyst"
    description = "Produces high-quality IRAC legal analysis with source grounding"

    async def run(self, input_data: dict) -> IRACOutput:
        if input_data.get("use_langgraph"):
            return await self._run_via_langgraph(input_data)
        return await self._run_legacy(input_data)

    async def _run_legacy(self, input_data: dict) -> IRACOutput:
        start = time.time()

        # TODO: Implement real GraphRAG retrieval + LLM call
        # For now, return structured mock
        output = IRACOutput(
            issue="Whether the defendant's conduct constitutes negligence under state law.",
            rule="A defendant is negligent if they breach a duty of care that proximately causes damages.",
            application="In this case, the defendant failed to maintain safe premises...",
            conclusion="The plaintiff is likely to succeed on a negligence claim.",
            sources=[{"title": "Sample Case", "url": "https://case.law/..."}],
            confidence=0.82,
            reasoning_trace=[
                "Retrieved 3 analogous precedents",
                "Applied IRAC framework",
            ],
        )

        latency = (time.time() - start) * 1000
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data=input_data,
            output_data=output.model_dump(),
            model="llama3.1:70b-q4_K_M",
            latency_ms=latency,
            confidence=output.confidence,
            sources=output.sources,
        )
        output.trace_id = trace_id
        return output

    async def _run_via_langgraph(self, input_data: dict) -> IRACOutput:
        """Spec 010 T-006: delegate to LegalWorkflow.

        We map the workflow's free-form ``answer`` into the IRAC fields by
        copying the answer text into ``application`` and surfacing the
        confidence + citations + Phoenix trace url. The richer
        issue/rule/conclusion split lands in BL-20260502-04 (LegalAnalyst
        backfill onto LegalWorkflow).
        """
        from lawgraph.agents_runtime.graphs import LegalWorkflow

        workflow = LegalWorkflow()
        question = input_data.get("text") or input_data.get("question") or ""
        result = await workflow.invoke(
            question,
            jurisdiction=input_data.get("jurisdiction"),
            case_id=input_data.get("case_id"),
        )

        sources = [
            {"title": c.text[:120], "url": c.source_url}
            for c in result.citations
            if c.source_url
        ]
        output = IRACOutput(
            issue=question[:200] or "(no question provided)",
            rule="See cited authorities below.",
            application=result.answer,
            conclusion=(
                "Pending human review — unverified citations detected."
                if result.human_approval_required
                else "Analysis complete; citations verified against the knowledge graph."
            ),
            sources=sources,
            confidence=result.confidence,
            reasoning_trace=[
                f"LangGraph thread {result.langgraph_thread_id}",
                f"latency {result.latency_ms} ms",
            ],
            trace_id=result.trace_id,
            phoenix_trace_url=result.phoenix_trace_url,
            langgraph_thread_id=result.langgraph_thread_id,
        )
        provenance.log_agent_call(
            agent_name=self.name,
            input_data=input_data,
            output_data=output.model_dump(),
            model=f"langgraph::{result.langgraph_thread_id}",
            latency_ms=result.latency_ms,
            confidence=result.confidence,
            sources=sources,
        )
        return output
