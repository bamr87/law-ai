# LawGraph AI — Agent Roles & Specifications

This document defines every agent that exists or is planned for LawGraph AI. All agents must follow the rules in `AGENTS.md`.

## Current Agents (MVP)

| Role                    | Type       | Core Responsibility                                      | Critical Tools                          | Structured Output                  | LegalBench Tasks Used          | HITL? |
|-------------------------|------------|----------------------------------------------------------|-----------------------------------------|------------------------------------|--------------------------------|-------|
| **Ingestion Scout**     | Data       | Parse opinions, extract citations (Eyecite) + entities, route low-confidence items to HITL queue. **Live** at [backend/lawgraph/ingestionapp/services/scout.py](../backend/lawgraph/ingestionapp/services/scout.py). | CourtListener client, Eyecite, Neo4j writer | `ExtractionResult` + confidence    | Entity extraction, NLI         | Yes (low confidence) |
| **Legal Analyst**       | Reasoning  | Produce IRAC brief, issue spotting, argument mapping     | GraphRAG retriever, LegalBench prompts  | `IRACOutput` + sources + risks     | Rule QA, Issue Spotting        | Optional |
| **Precedent Hunter**    | Retrieval  | Find on-point, analogous, and distinguishing cases       | Neo4j Cypher (shortest path, community), vector sim | `PrecedentList` + justification    | Precedent retrieval            | No    |
| **Logic Weaver**        | Reasoning  | Build argument maps, detect fallacies, score strength    | Custom reasoning prompts, entailment    | `ArgumentGraph` + fallacy list     | NLI, Fallacy detection         | No    |
| **Educator**            | Education  | Explain LSAT/Bar answers, generate drills, track skills  | Question bank, performance DB, subgraph | `Explanation` + next_recommended   | Reading Comp, Logical Reasoning| No    |
| **Orchestrator**        | Meta       | Decompose request, route to agents, manage state, HITL   | LangGraph state machine, shared memory  | `WorkflowTrace` + final artifact   | All (meta)                     | Yes (high-stakes) |

## Planned Agents (Post-MVP)

- **ContractRiskAssessor** — Clause classification + obligation extraction + risk scoring (uses CUAD + LEDGAR patterns)
- **StatuteChangeDetector** — Monitors legislation.gov.uk / EUR-Lex for amendments affecting user's saved cases
- **CaseOutcomePredictor** — Predicts likely outcome based on similar fact patterns + judge history (research only)
- **MultiJurisdictionComparator** — Side-by-side analysis across US/UK/EU on same legal issue

## Agent Implementation Template

Every agent must expose:

```python
class BaseLawGraphAgent:
    name: str
    description: str
    requires_human_approval: bool = False

    async def run(self, input: dict[str, Any]) -> BaseModel:
        ...

    async def stream(self, input: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        ...
```

See `prompts/new-agent.md` for the full implementation prompt.