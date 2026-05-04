# Tasks: 008 — Agent API Authentication

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.
- Each task references stable IDs from [spec.md](spec.md).

---

## T-001 — `app.core.security` dependency

- **Refs**: FR-1, FR-2, NFR-SEC-1, NFR-SEC-2, NFR-PERF-1, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/security.py` (new)
  - `backend/app/core/config.py` (edit — add `AGENT_API_KEY: str | None = None`)
  - `backend/tests/core/test_security.py` (new)
- **Steps**:
  1. Add `AGENT_API_KEY` to `Settings` (env-driven, default `None`).
  2. Implement `require_api_key(x_api_key: str | None = Header(None)) -> None` using `secrets.compare_digest` for the equality check.
  3. Cover all four branches (unset, missing, wrong, correct) plus a `compare_digest`-was-used assertion.
- **Verify**: `cd backend && pytest tests/core/test_security.py -q` passes; `mypy app/core/security.py --strict` clean.

## T-002 — Mount dependency on `/api/agents/*` + startup warning

- **Refs**: FR-3, FR-4, NFR-AUDIT-1, AC-1, AC-2, AC-3, AC-4, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/main.py` (edit — `dependencies=[Depends(require_api_key)]` on the agents router; add lifespan startup warning when key unset and `ENVIRONMENT != "development"`)
  - `backend/tests/api/test_agents.py` (edit — add `_isolate_auth` fixture; add four parametrized cases for AC-1..AC-4; add `caplog`-based AC-7 test)
- **Steps**:
  1. Import `Depends` and `require_api_key` in `app/main.py`; pass `dependencies=[...]` to `app.include_router(agents.router, ...)`.
  2. Inside `lifespan`, after registry registration, check `settings.AGENT_API_KEY` + `settings.ENVIRONMENT`; log a single WARNING when unset outside development.
  3. Update existing `test_agents.py` tests so they explicitly run with no key (default), preserving green suite.
  4. Add new tests covering missing / invalid / valid keys.
- **Verify**: `cd backend && pytest tests/api/test_agents.py -q` passes; `pytest --cov=app.api.agents --cov=app.core.security` ≥ 95 % on both; manual `curl -i http://localhost:8000/api/agents` with and without `X-API-Key` confirms the gate.

## T-003 — Frontend: forward `X-API-Key` for agent-ops calls

- **Refs**: FR-5, AC-6, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts` (edit — internal `agentFetch` wraps `fetch` and adds `X-API-Key` from `process.env.NEXT_PUBLIC_AGENT_API_KEY` when set; only used by `fetchAgents`/`fetchRuns`/`fetchBacklog`/`fetchSpecs`)
  - `frontend/__tests__/components/AgentDashboard.test.tsx` (edit — set `process.env.NEXT_PUBLIC_AGENT_API_KEY` per-test; MSW handlers assert the header is forwarded)
- **Steps**:
  1. Refactor the four `fetchAgents` / `fetchRuns` / `fetchBacklog` / `fetchSpecs` helpers to call a new private `agentFetch(path)` instead of `fetch(...)` directly. The helper attaches `X-API-Key` only when `process.env.NEXT_PUBLIC_AGENT_API_KEY` is non-empty.
  2. Add a vitest case that sets `vi.stubEnv('NEXT_PUBLIC_AGENT_API_KEY', 's3cret')`, mounts `AgentDashboard`, and asserts that all four MSW handlers received `X-API-Key: s3cret`.
  3. Keep an existing case with the env var unset to assert no header is sent (regression for default-open mode).
- **Verify**: `cd frontend && npm test -- --run` green; coverage stays ≥ 70 %.

## T-004 — Document new env vars

- **Refs**: FR-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `.env.example` (edit — add `AGENT_API_KEY=` and `NEXT_PUBLIC_AGENT_API_KEY=` with comments)
- **Steps**:
  1. Add a `### Auth (optional, recommended for non-localhost)` block to `.env.example` documenting both keys and the local-dev "leave blank" behaviour.
- **Verify**: `grep -n AGENT_API_KEY .env.example` shows both entries; `python scripts/spec_validator.py` and `python scripts/backlog_lint.py` exit 0.

## T-005 — Spec / BACKLOG hygiene

- **Refs**: constitution §11
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — move BL-20260429-13 from `## Open` to `## Done`; append new follow-up BL items)
  - `specs/008-agent-api-auth/spec.md` (edit `Status:` → `shipped` after green CI)
- **Steps**:
  1. After T-001..T-004 land green, set `Status: shipped` in [spec.md](spec.md).
  2. Move BL-20260429-13 to `## Done` with a one-line outcome and PR link.
  3. Mirror new follow-ups (see below) into `BACKLOG.md ## Open`.
- **Verify**: `python scripts/spec_validator.py && python scripts/backlog_lint.py && cd backend && pytest --cov=app --cov-fail-under=65` all exit 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests (AC-1..AC-7).
- `make lint && make test` green (backend ≥ 75 % cov on changed files, frontend ≥ 70 % cov).
- BL-20260429-13 moved to `## Done` in BACKLOG.md with PR link.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- **BL-20260430-07** — *feature, med* — Move the agent-ops API key out of the browser bundle by introducing a Next.js route handler (`app/agents/api/[...path]/route.ts`) that proxies `/api/agents/*` from the server, so `NEXT_PUBLIC_AGENT_API_KEY` can be replaced with a server-only `AGENT_API_KEY`. _Surfaced in:_ specs/008-agent-api-auth (R-2).
- **BL-20260430-08** — *feature, med* — Extend `require_api_key` (or add per-router variants) to gate `/api/analysis`, `/api/graph`, and `/api/lsat`. Today only `/api/agents/*` is protected. _Surfaced in:_ specs/008-agent-api-auth (NG3).
- **BL-20260430-09** — *feature, low* — Add per-key rate limiting on `/api/agents/*` (e.g. SlowAPI / Starlette middleware) so a leaked key cannot scrape the audit log at line speed. _Surfaced in:_ specs/008-agent-api-auth (NG2).
- **BL-20260430-10** — *doc-gap, low* — Add a `docs/security.md` capturing the threat model, the single-key MVP, and the upgrade path to per-user auth. Referenced by spec 008 §12 R-2. _Surfaced in:_ specs/008-agent-api-auth.
