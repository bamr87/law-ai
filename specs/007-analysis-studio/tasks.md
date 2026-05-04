# Tasks: 007 — Analysis Studio

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — Crew output `trace_id` plumbing

- **Refs**: FR-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/agents/crews/legal_analyst.py` (edit)
  - `backend/app/agents/crews/precedent_hunter.py` (edit)
- **Steps**:
  1. Add optional `trace_id: str | None` field to `IRACOutput` and
     `PrecedentList`.
  2. Capture the `trace_id` returned by `provenance.log_agent_call` and
     stamp it on the output before returning.
- **Verify**: `pytest backend/tests/api/test_analysis.py::test_run_analysis_happy_path -q`
  asserts both `trace_id`s are non-null.

## T-002 — `/api/analysis` rewrite (parallel run + HITL + audit)

- **Refs**: FR-1, FR-2, FR-3, FR-4, FR-5, NFR-AUDIT-1, NFR-HITL-1, NFR-PERF-1, NFR-SEC-1, AC-1, AC-2, AC-3, AC-4, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/api/analysis.py` (rewrite)
  - `backend/tests/api/test_analysis.py` (new — 6 tests)
- **Steps**:
  1. Pydantic-validated `AnalysisRequest` (text 1..20_000) — closes
     the empty/over-sized payload gap (NFR-SEC-1, AC-2).
  2. Run `LegalAnalyst` + `PrecedentHunter` via `asyncio.gather`
     (FR-2, AC-5).
  3. Build typed `AnalysisResponse` with `analysis_id`, mean
     `confidence`, `requires_human_review`, two `agent_trace` entries
     carrying `trace_id` + per-agent confidence (FR-3, FR-4, NFR-HITL-1).
  4. Emit umbrella `AnalysisStudio` audit event with
     `child_trace_ids: [...]` (FR-5, AC-3, NFR-AUDIT-1).
- **Verify**: `pytest backend/tests/api/test_analysis.py -q` — 6/6 green;
  full suite ≥ 75% coverage.

## T-003 — Frontend `/analysis` route + AnalysisStudio component

- **Refs**: FR-7, FR-8, AC-6, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/app/analysis/page.tsx` (new — server shell with metadata)
  - `frontend/components/AnalysisStudio.tsx` (new — client)
  - `frontend/lib/api.ts` (edit — typed `runAnalysis` + types, replaces
    untyped `analyzeCase`)
  - `frontend/__tests__/components/AnalysisStudio.test.tsx` (new — 5 tests)
- **Steps**:
  1. Server page renders header + `<AnalysisStudio />`.
  2. Client component exposes textarea, jurisdiction `<select>`, sample
     loader, IRAC card, precedents list with relevance bars, reused
     `<AgentTrace>` panel, HITL banner, footer chip with `analysis_id`
     and `trace_id`.
  3. MSW tests cover: form render, sample loader, full result
     rendering, HITL banner, error banner.
- **Verify**: `npm test -- --run` — 5/5 new + all prior pass.

## T-004 — BACKLOG hygiene + spec validation

- **Refs**: AC-1..AC-6 (gate), NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — append three new BL-20260429-2x items)
- **Verify**:
  - `python3 scripts/spec_validator.py` PASS.
  - `python3 scripts/backlog_lint.py` PASS.
  - Backend `pytest -q` green; frontend `npm test -- --run` green.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `pytest -q` green (≥ 75% coverage); `npm test -- --run` green.
- `## Follow-ups Discovered` section below populated and mirrored to
  `BACKLOG.md`.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a
> `BL-YYYYMMDD-NN` id.

- **BL-20260429-24** — *feature, med* — Stream agent trace events to the
  `/analysis` UI via SSE so users see `LegalAnalyst` → `PrecedentHunter`
  progress instead of waiting for a single JSON response.
- **BL-20260429-25** — *feature, med* — Persist analyses (request +
  response + trace_ids) in Postgres so users can revisit a run by
  `analysis_id` and the `/agents/runs/{trace_id}` drill-down
  (BL-20260429-14) can join across child traces.
- **BL-20260429-26** — *feature, low* — "Save & share" — let signed-in
  users bookmark an analysis with a slug and produce a shareable URL.
- **BL-20260429-27** — *test-gap, low* — Add a Playwright smoke test
  hitting `/analysis` end-to-end against a Docker stack (form fill →
  result render → trace ID copy).
