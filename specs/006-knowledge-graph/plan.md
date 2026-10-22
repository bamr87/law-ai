# Plan: 006 — Knowledge Graph Explorer

## Approach

Three layers, each hermetically testable:

1. **Cypher layer** — `app/db/graph_queries.py`. Three async functions
that take an `AsyncSession` and return typed dicts. Same shape as `app/db/citation_resolver.py` so `FakeAsyncSession` from `tests/db/test_citation_resolver.py` style works directly.
2. **Read API** — `app/api/graph.py`. Three endpoints. A module-level
`_open_session()` indirection keeps tests free of Neo4j: tests monkeypatch it to yield a `FakeAsyncSession`. Catches Neo4j-shaped exceptions and returns `available=false` (NFR-DEGRADE-1).
3. **UI** — `app/graph/page.tsx` server shell + `components/KnowledgeGraph.tsx`
client component that composes a refactored `GraphViewer.tsx` (now a true Cytoscape canvas, closing BL-20260430-05).

## File Layout

```
backend/app/db/graph_queries.py            (new, ~120 LOC)
backend/app/api/graph.py                   (new, ~140 LOC)
backend/app/main.py                        (edit — mount router)
backend/tests/db/test_graph_queries.py     (new)
backend/tests/api/test_graph.py            (new)

frontend/app/graph/page.tsx                (new, server shell)
frontend/components/KnowledgeGraph.tsx     (new, client)
frontend/components/GraphViewer.tsx        (rewrite — real Cytoscape)
frontend/lib/api.ts                        (edit — graph fetchers + types)
frontend/__tests__/components/KnowledgeGraph.test.tsx (new, MSW-mocked)
```

## Why These Choices

- **Session-factory indirection**: matches the pattern already used in spec
002's `densify_extraction`. Tests stay docker-free; integration test is filed as a follow-up.
- **Graceful degradation over 503**: a 5xx response would crash the
Knowledge Graph panel. Returning `{"available": false}` lets the UI show a friendly banner and keeps the rest of the app responsive.
- **Cytoscape over React Flow**: spec 001's data model + AGENTS.md both
call out Cytoscape; it's already in `package.json`. Dynamic-import to avoid SSR pitfalls.
- **Refactor `GraphViewer.tsx` rather than delete**: keeps the existing
import surface (used by `KnowledgeGraph` here, and by future analysis views) and turns the open TODO into shipped code.

## Cross-Cutting Concerns

- **Provenance**: every endpoint records via `provenance.log_graph_query` so the Agent Ops dashboard sees the hits.
- **Audit/HITL**: read-only routes; no HITL needed.
- **Tests**: ≥ 75% backend (new modules ≥ 80%); ≥ 70% frontend.
Cytoscape is dynamically imported so vitest renders an empty canvas div — assertions target headings + element count via `data-testid`.

## Risk Mitigations

- **R-1 (bundle size)**: dynamic `await import('cytoscape')` inside the
GraphViewer effect; Next.js code-splits it into a chunk only loaded on `/graph`.
- **R-2 (huge neighborhoods)**: the `neighborhood` Cypher uses
`LIMIT $limit` on both citation and cited-case branches; API caps `limit ≤ 200`.

## Out-of-Scope (Tracked as Follow-ups)

- Path queries, court/date filters, authn/z, WebSocket push, integration test against a real Neo4j (mirrors BL-20260429-10 for resolver).
