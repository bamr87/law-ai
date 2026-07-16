# Law AI Architecture

## High-Level Overview

```mermaid
flowchart TB
    subgraph Public["Public Legal Sources"]
        CL["CourtListener + RECAP"]
        CAP["Harvard CAP Bulk"]
        UK["legislation.gov.uk"]
        EU["EUR-Lex"]
    end

    subgraph Backend["Backend (Python/Django ASGI)"]
        Ingestion["Ingestion Scout Agent"]
        Agents["Multi-Agent Crews\n(CrewAI + LangGraph)"]
        Neo4j["Neo4j Knowledge Graph"]
        Postgres["PostgreSQL"]
        Vector["Chroma / Weaviate"]
        LLM["Ollama (Local LLMs)"]
    end

    subgraph Frontend["Next.js Frontend"]
        Graph["Interactive Knowledge Graph\n(Cytoscape.js)"]
        Studio["Analysis Studio\n(Live Agent Traces)"]
        LSAT["LSAT Learning Lab"]
        Library["Case Library + Hybrid Search"]
    end

    Public --> Ingestion
    Ingestion --> Neo4j
    Ingestion --> Vector
    Agents --> Neo4j
    Agents --> Vector
    Agents --> LLM
    Frontend --> Agents
    Neo4j -. Live Updates .-> Graph
```

**Key Design Decisions**:
- **Agent Orchestration**: Hybrid CrewAI (fast role-based) + LangGraph (stateful + auditable)
- **Knowledge Representation**: Neo4j as single source of truth for legal relationships
- **Retrieval**: Hybrid GraphRAG (Cypher traversals + vector similarity)
- **Privacy**: Ollama local by default; full audit trail of every LLM call

---

## Component Responsibilities

| Component              | Responsibility                                                                 | Key Files |
|------------------------|----------------------------------------------------------------------------------|-----------|
| **Ingestion Scout**    | Fetch → Parse (Eyecite) → Extract (Blackstone + LLM) → Commit to Neo4j          | `backend/law_ai/ingestionapp/`, `agents/crews/ingestion_scout/` |
| **Agent Crews**        | Specialized legal reasoning (Analyst, Precedent Hunter, Logic Weaver, Educator) | `backend/law_ai/agents_runtime/crews/` |
| **Orchestrator**       | LangGraph state machine, routing, HITL gates, provenance logging                | `backend/law_ai/agents_runtime/graphs/orchestrator.py` |
| **GraphRAG Engine**    | Hybrid retrieval (vector + Cypher) + community summaries                        | `backend/law_ai/agents_runtime/tools/graph_rag.py` |
| **API Layer**          | Django REST Framework views for analysis, graph queries, ingestion, LSAT (+ Channels consumers for agent streaming) | `backend/law_ai/{analysis,graph,lsat,agentsapi,ingestionapp}/` |
| **Frontend**           | Interactive graph, real-time agent streaming, LSAT practice, library            | `frontend/app/` + `components/GraphViewer.tsx` |
| **Evaluation**         | LegalBench harness + custom legal reasoning tests                               | `backend/law_ai/eval/` |
| **Autonomy Loop**      | Scheduled cycles (corpus growth, test synthesis, digest) controlled by `AUTONOMY_ENABLED` kill-switch; single audited entry point via `law_ai.core.autonomy.run_cycle`; every cycle emits paired provenance events | `backend/law_ai/core/autonomy.py`, `celery.py`, `agents_runtime/crews/test_synthesizer/`, `agents_runtime/graphs/topic_frontier.py` |

---

## Data Flow Example: "Analyze this case + find precedents"

1. User uploads case or selects from library → `POST /api/analysis`
2. Orchestrator creates LangGraph run → routes to `LegalAnalyst` + `PrecedentHunter` in parallel
3. `LegalAnalyst` produces IRAC + structured output (grounded via GraphRAG)
4. `PrecedentHunter` runs Cypher query for analogous cases + vector similarity
5. Results streamed to frontend via WebSocket
6. User approves → results committed to project workspace + graph updated
7. Full trace (prompts, tool calls, retrievals) saved in `provenance` table

---

## Autonomy Loop (Spec 018)

The autonomy loop runs inside the same Docker Compose stack as the main API. It is disabled by default (`AUTONOMY_ENABLED=false`) per [docs/constitution.md](constitution.md) §12 invariant I3 (kill-switch).

```mermaid
flowchart LR
  Beat["Celery Beat\n(3 schedules)"] --> Entry["autonomy.run_cycle()\n(single audited entry point)"]
  Entry -->|corpus_growth| TF["TopicFrontier LangGraph"]
  Entry -->|test_pillar| TS["TestSynthesizer CrewAI"]
  Entry -->|digest| Digest["compose_digest()"]
  TF -->|dispatch via| Scout["IngestionScout\n(HITL gate preserved)"]
  TS -->|writes| Proposed["*.proposed.py\n(pending human review)"]
  Digest -->|writes| DigestFile["var/autonomy/digest-YYYY-MM-DD.md"]
  Entry --> Provenance["AuditEvent\n(autonomy_cycle.start/end)"]
```

See [ADR 0003](adr/0003-autonomy-orchestrator.md) for the full design rationale and the six invariants (I1–I6).

The `baseline.json` for LegalBench regression tracking will be committed after the first green harness run; its commit SHA will be recorded in [docs/legalbench.md](legalbench.md) `## Baseline scores`.

---

## Technology Choices Rationale

- **Neo4j over pure vector DB**: Legal reasoning is heavily relational (citations, overruling, same-jurisdiction, same-issue). Graph traversals are more precise than embedding similarity alone.
- **CrewAI + LangGraph**: CrewAI gives fast, readable role-based crews. LangGraph gives production-grade state, checkpointing, and time-travel debugging (essential for legal audit).
- **Ollama default**: Keeps all sensitive legal data on-prem. Supports quantized models for consumer hardware.
- **Cytoscape.js**: Best-in-class performance for large interactive graphs (10k+ nodes) with excellent React integration.

See `docs/data-model.md` for full Neo4j schema and `docs/agent-roles.md` for detailed agent specs.