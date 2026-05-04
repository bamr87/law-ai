# Tasks: 003 — Agent Operations Dashboard

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — `audit_store` module

- **Refs**: FR-1, NFR-AUDIT-1, NFR-IDEMPOTENT-1, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/audit_store.py` (new)
  - `backend/app/core/config.py` (edit — add `AUDIT_PATH`, `MAX_AUDIT_LINES`, `KEEP_AUDIT_LINES`)
  - `backend/tests/core/__init__.py` (new)
  - `backend/tests/core/test_audit_store.py` (new)
- **Steps**:
  1. Implement `record(event)` with try/except → log warning, never raise.
  2. Implement `tail(limit)` returning newest-first list.
  3. Implement `_rotate_if_needed()` truncating to `KEEP_AUDIT_LINES` when over `MAX_AUDIT_LINES`.
- **Verify**: `pytest backend/tests/core/test_audit_store.py -q` passes; coverage ≥ 90 % on the module.

## T-002 — Tee provenance into audit store

- **Refs**: FR-2, NFR-AUDIT-1, AC-1, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/provenance.py` (edit)
- **Steps**:
  1. After each `logger.info(...)` call inside `log_request`, `log_agent_call`, `log_graph_query`, also call `audit_store.record(log_entry)`.
  2. Wrap the `record` call in a try/except that logs at WARNING and swallows.
- **Verify**: existing tests stay green; new test in `test_audit_store.py` covers the failure path.

## T-003 — `/api/agents` router

- **Refs**: FR-3, FR-4, FR-5, FR-6, NFR-PERF-1, NFR-SEC-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/api/agents.py` (new)
  - `backend/app/main.py` (edit — mount router, remove `# TODO: add registry endpoint` comment)
  - `backend/tests/api/test_agents.py` (new)
- **Steps**:
  1. Implement four endpoints; each delegates to a small pure helper for parsing.
  2. Reuse `scripts.backlog_lint.BULLET_RE` for the BACKLOG parser.
  3. Add hermetic tests with a `tmp_path` audit file + `monkeypatch` on settings.
- **Verify**: `pytest backend/tests/api -q`; spec_validator still green.

## T-004 — Frontend dashboard route

- **Refs**: FR-7, AC-6, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/app/agents/page.tsx` (new — server shell)
  - `frontend/components/AgentDashboard.tsx` (new — client polling)
  - `frontend/lib/api.ts` (edit — `fetchAgents`, `fetchRuns`, `fetchBacklog`, `fetchSpecs`)
  - `frontend/__tests__/components/AgentDashboard.test.tsx` (new — MSW-mocked)
- **Steps**:
  1. Server component renders `<AgentDashboard />`.
  2. Client component polls four endpoints in parallel every 5 s; first render shows "Loading…" placeholders.
  3. Handle and surface fetch errors per panel without crashing the page.
- **Verify**: `cd frontend && npm test -- --run`; vitest coverage ≥ 70 %.

## T-005 — Documentation polish

- **Refs**: NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/main.py` (edit — root `agents` link now points to `/api/agents` for real)
  - `backend/app/core/config.py` (edit — settings docstring)
- **Steps**: Already covered as side-effects of T-003; no separate file edits needed beyond the comments touched there.
- **Verify**: `python3 scripts/spec_validator.py` PASS.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green (backend ≥ 75 % cov, frontend ≥ 70 % cov).
- BL-20260430-02 moved to `## Done` in BACKLOG.md.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- **BL-20260429-13** — *feature, high* — Add authn/z to `/api/agents/*` routes before the dashboard is exposed beyond localhost (currently NG1 — local-first MVP).
- **BL-20260429-14** — *feature, med* — Add a single-run drill-down view (`/agents/runs/{trace_id}`) showing full input/output, sources, and the prompt template version that produced it.
- **BL-20260429-15** — *feature, med* — Add HITL action endpoints (`approve` / `reject`) so reviewers can resolve quarantined items from the dashboard rather than `psql`.
- **BL-20260429-16** — *infra, low* — Replace polling with WebSocket push once we have > 5 concurrent reviewers (current 5 s polling is wasteful for a single-user laptop only at scale).
