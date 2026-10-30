# Spec: Knowledge Graph Explorer

- **ID**: 006-knowledge-graph
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: User request 2026-04-29 — "build the knowledge graph"
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1–11.

## 1. Problem & Motivation

The home page advertises an interactive Knowledge Graph at `/graph`, but the route 404s. Backend has Cypher helpers and migrations (`Case`, `Citation`, `CITES`, `HAS_CITATION`) plus an ingestion pipeline that already populates those nodes (specs 001 + 002), but no read API surfaces them. The [GraphViewer.tsx](../../frontend/components/GraphViewer.tsx) component is a stub that just prints "Cytoscape.js integration pending" — closing BL-20260430-05 also requires that this is wired up. Without a UI on top of Neo4j, the "Graph-Native Thinking" pillar of [AGENTS.md](../../AGENTS.md) is invisible to users and reviewers.

## 2. Goals

- G1: Read-only `/api/graph/*` surface that exposes stats, case search, and per-case neighborhood traversal — backed by `app.db.graph_queries`.
- G2: Frontend `/graph` route that renders a Cytoscape canvas wired to a case picker and a stats strip.
- G3: Graceful degradation when Neo4j is unavailable (returns
`{"available": false}` payloads instead of 500s) so the dashboard is resilient on a fresh laptop.
- G4: Close BL-20260430-05 by replacing the GraphViewer stub with a real Cytoscape integration.

## 3. Non-Goals

- NG1: Mutation / write endpoints — read-only MVP.
- NG2: Authn/z (same posture as spec 003 — local-first, follow-up tracked).
- NG3: Vector search / GraphRAG retrieval — that lands separately when the PrecedentHunter agent is wired up.
- NG4: Real-time graph updates via WebSocket — polling on demand is enough.

## 4. User Stories

- As a **researcher**, I want to search a case by title or id and see its citation neighborhood so I can audit precedent links visually.
- As a **maintainer**, I want a stats strip showing total `Case`,
`Citation`, and `CITES` counts so I can confirm ingestion is producing edges, not just orphan nodes.
- As a **reviewer**, I want the `/graph` page to load even when Neo4j is down so I can still triage other dashboards.

## 5. Functional Requirements

- **FR-1**: New module `app.db.graph_queries` exposes three async helpers taking an `AsyncSession`:
  - `stats(session) -> {cases, citations, cites_edges}`
  - `list_cases(session, q, limit) -> [{id, title, court, decided_at}]`
  - `neighborhood(session, case_id, limit) -> {nodes, edges}` (Cytoscape elements shape).
- **FR-2**: New FastAPI router mounted at `/api/graph`:
  - `GET /api/graph/stats`
  - `GET /api/graph/cases?q=&limit=` (1 ≤ limit ≤ 100, default 25)
  - `GET /api/graph/neighborhood/{case_id}?limit=` (1 ≤ limit ≤ 200, default 50)
- **FR-3**: Each endpoint logs via `provenance.log_graph_query` (NFR-AUDIT-1).
- **FR-4**: When the underlying Neo4j call raises `ServiceUnavailable`,
`AuthError`, `ConfigurationError`, or any `Exception` from the driver, endpoints return HTTP 200 with `{"available": false, ...}` and an empty payload (NFR-DEGRADE-1). Errors are logged at WARNING.
- **FR-5**: Frontend `app/graph/page.tsx` server shell + new client component `components/KnowledgeGraph.tsx` that:
  - Fetches `/api/graph/stats` and `/api/graph/cases`.
  - On case selection, fetches `/api/graph/neighborhood/{id}` and renders a Cytoscape canvas (cose-style force layout, Case nodes blue, Citation nodes amber, `CITES` blue edges, `HAS_CITATION` grey edges).
  - Shows a banner when `available: false`.
- **FR-6**: `lib/api.ts` gains `fetchGraphStats`, `fetchGraphCases`, `fetchGraphNeighborhood` typed clients.
- **FR-7**: Replace [GraphViewer.tsx](../../frontend/components/GraphViewer.tsx)
stub: it now accepts `{ elements }` and renders Cytoscape (closes BL-20260430-05). KnowledgeGraph composes it.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: Each `/api/graph/*` endpoint p95 < 500 ms against a 10k-node sample (Cypher uses `LIMIT` and indexed properties only).
- **NFR-AUDIT-1**: Every endpoint records a `graph_query` provenance event.
- **NFR-DEGRADE-1**: Neo4j outage never returns 5xx — payloads degrade to `available: false`.
- **NFR-SEC-1**: All Cypher uses parameter binding — no string interpolation of user input. `q` filter is matched via `CONTAINS` against parameter.
- **NFR-COVERAGE-1**: Backend coverage ≥ 75% repo-wide; new modules ≥ 80%.
- **NFR-LICENSE-1**: Cytoscape.js (MIT) already in `package.json`. No new runtime deps.

## 7. Data Model Impact

- No schema changes. Reads existing `Case`, `Citation`, `HAS_CITATION`, `CITES` nodes/edges from spec 001 + spec 002.

## 8. API Surface

```
GET /api/graph/stats
  -> {"available": bool, "cases": int, "citations": int, "cites_edges": int}

GET /api/graph/cases?q=string&limit=25
  -> {"available": bool, "cases": [{"id","title","court","decided_at"}], "count": int}

GET /api/graph/neighborhood/{case_id}?limit=50
  -> {"available": bool, "nodes": [{"data":{"id","label","type","court?"}}],
      "edges": [{"data":{"id","source","target","type"}}]}
```

## 9. Agent / Crew Impact

- No new agent. Sets the foundation that PrecedentHunter and LegalAnalyst will read from once their TODOs are resolved (BL-20260430-03/04).

## 10. Acceptance Criteria

- **AC-1**: `GET /api/graph/stats` returns `available=true` and integer counts when the (fake) session yields valid records (verifies FR-1, FR-2).
- **AC-2**: `GET /api/graph/cases?q=roe&limit=3` returns at most 3 cases whose titles match (verifies FR-2 + NFR-SEC-1 parameter binding).
- **AC-3**: `GET /api/graph/neighborhood/case-a` returns Cytoscape-shaped payload with `nodes` and `edges` arrays (verifies FR-2).
- **AC-4**: When the session factory raises `ServiceUnavailable`, every
endpoint returns HTTP 200 with `available=false` and empty data (verifies FR-4, NFR-DEGRADE-1).
- **AC-5**: A provenance `graph_query` event is recorded per endpoint hit (verifies FR-3, NFR-AUDIT-1).
- **AC-6**: Frontend `/graph` page renders the headings "Knowledge Graph",
"Cases", and "Neighborhood" with MSW-mocked API; selecting a case fetches the neighborhood and the Cytoscape container is mounted (verifies FR-5, FR-7).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp. Read-only visualization layer.

## 12. Risks & Open Questions

- **R-1**: Cytoscape ships ~150 KB of JS. Mitigation: dynamic `import()` inside the client component so the rest of the app stays unaffected.
- **R-2**: A very wide neighborhood query could return thousands of
citations for a single landmark case. Mitigation: hard `LIMIT` bound in Cypher + API param cap of 200.

## 13. Out of Scope / Follow-ups

- Path queries (shortest path between two cases).
- Filtering by court / date in the UI.
- Authn/z + WebSocket push.
