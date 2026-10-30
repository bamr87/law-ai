# Tasks: 009 — Extend API Authentication

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.
- Each task references stable IDs from [spec.md](spec.md).

---

## T-001 — `make_api_key_dep` factory in `app.core.security`

- **Refs**: FR-1, FR-2, FR-3, NFR-SEC-1, NFR-SEC-2, NFR-PERF-1, AC-8
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/security.py` (edit — add `make_api_key_dep(*setting_names)`; refactor `require_api_key` to call it)
  - `backend/app/core/config.py` (edit — add `ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY` settings)
  - `backend/tests/core/test_security.py` (edit — add factory cases incl. precedence)
- **Steps**:
  1. Add the three per-router settings, all default `None`, with docstrings noting fallback semantics.
  2. Implement `make_api_key_dep(*setting_names) -> Callable[..., None]` that builds a `Depends`-able callable. Resolution: first non-empty `getattr(settings, name)` wins; all empty → open.
  3. Use `secrets.compare_digest` for the equality check (NFR-SEC-1).
  4. Refactor `require_api_key = make_api_key_dep("AGENT_API_KEY")` so spec-008 call sites are unchanged.
  5. Add tests: empty, missing, wrong, correct (single name); precedence (override beats fallback); fallback only; all-empty.
- **Verify**: `cd backend && pytest tests/core/test_security.py -q` passes; `mypy app/core/security.py --strict` clean.

## T-002 — Mount per-router dependencies in `app.main`

- **Refs**: FR-4, FR-5, NFR-AUDIT-1, NFR-COMPAT-1, AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-9
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/main.py` (edit — three new `Depends` on `include_router`; expand startup warning)
  - `backend/tests/conftest.py` (edit — autouse `_reset_api_keys` fixture neutralising `AGENT_API_KEY`, `ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY`)
  - `backend/tests/api/test_analysis.py` (edit — add AC-1..AC-4 cases)
  - `backend/tests/api/test_graph.py` (edit — add AC-1..AC-4 cases)
  - `backend/tests/api/test_lsat.py` (edit — add AC-1..AC-6 cases incl. AC-5/AC-6 isolation + override precedence)
  - `backend/tests/api/test_health.py` (edit — AC-7: `/health` open under all key configs)
  - `backend/tests/api/test_agents.py` (edit if needed — extend the AC-9 warning test to assert all four router groups are listed)
- **Steps**:
  1. Mount each feature router with `dependencies=[Depends(make_api_key_dep("<ROUTER>_API_KEY", "AGENT_API_KEY"))]`.
  2. In `lifespan`, when `AGENT_API_KEY` is unset and `ENVIRONMENT != "development"`, log one WARNING listing the unprotected router groups (`agents,analysis,graph,lsat`).
  3. Add the autouse fixture to `backend/tests/conftest.py` so every test starts with all four keys set to `None` (per-test `monkeypatch` still wins).
  4. Add per-router `with_shared_key` and `with_router_key` fixtures in each test module, and add the AC-numbered cases.
- **Verify**: `cd backend && pytest -q` passes; coverage stays ≥ 75 %.

## T-003 — Frontend `apiFetch` consolidation + header forwarding

- **Refs**: FR-6, AC-10, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts` (edit — introduce `apiFetch(path, init?)`; refactor `runAnalysis`, `getGraph`, `gradeLsat`, `getJson`, `agentFetch` to delegate)
  - `frontend/__tests__/components/AnalysisStudio.test.tsx` (edit — add a "forwards X-API-Key when env set" case using `vi.stubEnv`)
  - `frontend/__tests__/components/KnowledgeGraph.test.tsx` (edit — same)
- **Steps**:
  1. Implement `apiFetch(path: string, init?: RequestInit): Promise<Response>` in `lib/api.ts` that merges `init.headers` with `{ 'X-API-Key': ... }` when `process.env.NEXT_PUBLIC_AGENT_API_KEY` is non-empty.
  2. Refactor existing helpers to use `apiFetch`. Keep `agentFetch` as a tiny wrapper for source-compat with spec 008 callers.
  3. Add MSW handler assertions on `/api/analysis` and `/api/graph/*` covering both env-unset and env-set cases.
- **Verify**: `cd frontend && npm test -- --run` green; coverage stays ≥ 70 %.

## T-004 — Document new env vars

- **Refs**: FR-7, R-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `.env.example` (edit — add `ANALYSIS_API_KEY=`, `GRAPH_API_KEY=`, `LSAT_API_KEY=` under the existing Auth block; document fallback semantics and the spec-008 → 009 widening)
- **Steps**:
  1. Append the three per-router keys with comments explaining the override-then-fallback rule.
  2. Add a one-liner that calls out the widening: "As of spec 009, AGENT_API_KEY also gates /api/analysis, /api/graph/*, and /api/lsat/* unless overridden."
- **Verify**: `grep -nE 'ANALYSIS_API_KEY|GRAPH_API_KEY|LSAT_API_KEY' .env.example` shows all three.

## T-005 — Spec / BACKLOG hygiene

- **Refs**: constitution §11
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — move BL-20260430-08 from `## Open` to `## Done`; append new follow-up BL items)
  - `specs/009-extend-api-auth/spec.md` (edit `Status:` → `shipped` after green CI)
- **Steps**:
  1. After T-001..T-004 land green, set `Status: shipped` in [spec.md](spec.md).
  2. Move BL-20260430-08 to `## Done` with a one-line outcome.
  3. Mirror new follow-ups (see below) into `BACKLOG.md ## Open`.
- **Verify**: `python scripts/spec_validator.py && python scripts/backlog_lint.py && cd backend && pytest --cov=app --cov-fail-under=65` all exit 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests (AC-1..AC-10).
- `make lint && make test` green (backend ≥ 75 % cov on changed files, frontend ≥ 70 % cov).
- BL-20260430-08 moved to `## Done` in BACKLOG.md.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI (`scripts/spec_validator.py`) checks this section exists. CI (`scripts/backlog_lint.py`) checks the BACKLOG mirror.

- **BL-20260430-11** — *test-gap, low* — Add a Playwright smoke test that toggles `AGENT_API_KEY`/`NEXT_PUBLIC_AGENT_API_KEY` and verifies all four pages (`/agents`, `/analysis`, `/graph`, `/lsat`) load end-to-end against a Docker stack. _Surfaced in:_ specs/009-extend-api-auth.
- **BL-20260430-12** — *infra, low* — Have `app/main.py` lifespan refuse to start when `ENVIRONMENT="production"` and `AGENT_API_KEY` is unset (today it only warns). Promotes the dev-friendly default into a production guard rail. _Surfaced in:_ specs/009-extend-api-auth.
- **BL-20260430-13** — *doc-gap, low* — Document the per-router fallback chain (`<ROUTER>_API_KEY` → `AGENT_API_KEY`) in [docs/architecture.md](../../docs/architecture.md), including a short table mapping routes → settings. _Surfaced in:_ specs/009-extend-api-auth.
