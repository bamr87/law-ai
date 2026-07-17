# Tasks: 006 — Knowledge Graph Explorer

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — `graph_queries` Cypher helpers

- **Refs**: FR-1, NFR-PERF-1, NFR-SEC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/db/graph_queries.py` (new)
  - `backend/tests/db/test_graph_queries.py` (new)
- **Steps**:
  1. Implement `stats`, `list_cases`, `neighborhood` against an
     `AsyncSession`. Every query bound by `LIMIT $limit`.
  2. Hermetic tests using a `FakeAsyncSession` (matches the pattern in
     `tests/db/test_citation_resolver.py`).
- **Verify**: `pytest backend/tests/db/test_graph_queries.py -q`; module
  coverage ≥ 80%.

## T-002 — `/api/graph/*` router

- **Refs**: FR-2, FR-3, FR-4, NFR-AUDIT-1, NFR-DEGRADE-1, AC-1, AC-2, AC-3, AC-4, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/api/graph.py` (new)
  - `backend/app/main.py` (edit — mount router)
  - `backend/tests/api/test_graph.py` (new)
- **Steps**:
  1. Three endpoints (`stats`, `cases`, `neighborhood/{case_id}`) all
     delegating to `graph_queries` via a `_safe_run` wrapper.
  2. `_open_session` indirection so tests monkeypatch a fake session
     without spinning up Neo4j.
  3. Provenance via `provenance.log_graph_query` after each successful
     call.
  4. `available: false` payloads on any exception (NFR-DEGRADE-1).
- **Verify**: `pytest backend/tests/api/test_graph.py -q`; spec_validator
  green.

## T-003 — Frontend `/graph` route + Cytoscape

- **Refs**: FR-5, FR-6, FR-7, AC-6, NFR-LICENSE-1, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/app/graph/page.tsx` (new — server shell)
  - `frontend/components/KnowledgeGraph.tsx` (new — client)
  - `frontend/components/GraphViewer.tsx` (rewrite — Cytoscape canvas, closes BL-20260430-05)
  - `frontend/lib/api.ts` (edit — `fetchGraphStats`, `fetchGraphCases`, `fetchGraphNeighborhood` + types)
  - `frontend/__tests__/components/KnowledgeGraph.test.tsx` (new — MSW-mocked)
- **Steps**:
  1. Server shell renders header + `<KnowledgeGraph />`.
  2. Client component fetches stats + cases on mount, debounced search,
     auto-selects first case, fetches neighborhood on selection.
  3. `GraphViewer` dynamically imports `cytoscape` to keep the bundle
     out of other routes (R-1).
  4. Banner when any endpoint returns `available: false` (FR-5).
- **Verify**: `npm test -- --run`; vitest 9/9 pass.

## T-004 — Documentation polish

- **Refs**: AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — move BL-20260430-05 from Open → Done; append three
    new follow-ups)
- **Verify**: `python3 scripts/backlog_lint.py` PASS.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `pytest -q` green (≥ 75% coverage); `npm test -- --run` green.
- BL-20260430-05 moved to `## Done` in BACKLOG.md.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a
> `BL-YYYYMMDD-NN` id.

- **BL-20260429-21** — *test-gap, med* — Docker-backed integration test
for `app.db.graph_queries.neighborhood` against a real Neo4j; mirrors the gap filed for the citation resolver (BL-20260429-10).
- **BL-20260429-22** — *feature, med* — Add a "shortest path" endpoint
(`/api/graph/path?from=&to=`) so the UI can highlight precedent chains between two cases.
- **BL-20260429-23** — *feature, low* — UI filters for the case picker
(court, date range) and a sidebar inspector that shows the selected node's full properties + source URL.
