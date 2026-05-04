# Plan: 008 — Agent API Authentication

## Approach

Three small, decoupled changes, each independently testable:

1. **Auth dependency** — `app/core/security.py` exposes one pure helper (`require_api_key`) that reads `settings.AGENT_API_KEY` and either short-circuits, raises 401 missing, or raises 401 invalid via constant-time compare. No I/O, no DB.
2. **Wire-up** — `app/api/agents.py` keeps its existing route definitions; the dependency is attached at the `app.include_router(...)` site in `app/main.py` so the router itself stays auth-agnostic and reusable in tests. A startup warning is emitted from `lifespan` when the key is unset outside of `development`.
3. **Frontend** — `frontend/lib/api.ts` adds a single internal helper that injects `X-API-Key` for the four `fetch*` agent-ops calls. The MSW test fixture asserts the header is forwarded.

## File Layout

```
backend/app/core/security.py                (new, ~30 LOC)
backend/app/core/config.py                  (edit — add AGENT_API_KEY)
backend/app/main.py                         (edit — Depends + startup warning)
backend/tests/core/test_security.py         (new)
backend/tests/api/test_agents.py            (edit — +auth fixtures, +AC-2..AC-4)

frontend/lib/api.ts                         (edit — agentFetch wrapper)
frontend/__tests__/components/AgentDashboard.test.tsx (edit — assert header)

.env.example                                (edit — document both keys)
```

## Why These Choices

- **Single shared key over JWT/OAuth**: matches NG1 / G1. The current threat model is "developer wants to expose the dashboard on a tailnet without leaking provenance to the LAN." A static key is enough; introducing a user model now would balloon scope and pull in a Postgres schema migration with no immediate consumer.
- **`secrets.compare_digest` over `==`**: NFR-SEC-1; eliminates a textbook timing-side-channel even though the key is short-lived for now.
- **Dependency mounted at `include_router`, not on each route**: keeps `app.api.agents` test-importable without monkey-patching the dependency, and means future specs only need to change one line in `main.py`.
- **`NEXT_PUBLIC_AGENT_API_KEY`**: documented as **not secret** (R-2). The trade-off is that the dashboard works in a static client bundle today; tomorrow's follow-up moves it behind a Next.js route handler.

## Provenance & Audit Hook-up

No new provenance events. The existing `provenance_middleware` already logs every HTTP request (including 401s) via `app.core.provenance.log_request`, which already tees into `audit_store`. Denied requests therefore appear in the dashboard's "Recent Runs" feed (visible to operators with the key).

The configured key value is **never** added to any log entry (NFR-SEC-2): we log only `request.method`, `path`, and `status_code` — the `X-API-Key` header is never read by the provenance layer.

## HITL Gates

None. This spec does not change any HITL path; the existing ingestion-quarantine gate (spec 004) remains untouched.

## Test Strategy

- **Unit (`test_security.py`)**: parametrized cases for unset key, missing header, wrong header, correct header; one test verifies `secrets.compare_digest` is the comparator (AC-5).
- **API (`test_agents.py`)**: extend the existing `_isolate_audit` fixture with an `_isolate_auth` fixture that patches `settings.AGENT_API_KEY`. Add three test cases per FR-3 covering AC-1..AC-4 against `/api/agents`, `/api/agents/runs`, `/api/agents/backlog`, `/api/agents/specs`.
- **Startup warning (AC-7)**: use `caplog` against `app.main`'s `lifespan` by constructing the app with `monkeypatch` on `settings.ENVIRONMENT` and `settings.AGENT_API_KEY`.
- **Frontend (`AgentDashboard.test.tsx`)**: extend the MSW handlers to assert `request.headers.get('X-API-Key') === 's3cret'` when the env var is set; reset between tests.
- **No LegalBench delta needed** (NFR — no reasoning code touched).

## Rollout

- Local dev: no action — key unset → behavior unchanged. `make dev` continues to work.
- Staging / tailnet: operator sets `AGENT_API_KEY` in backend `.env` and `NEXT_PUBLIC_AGENT_API_KEY` in frontend `.env`; `docker compose up --build` picks both up.
- No backfill, no migration, no feature flag beyond the key itself.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Operator forgets frontend key after enabling backend | med | low | Per-panel 401 error rendered by existing error handler; `.env.example` callout. |
| Key bundled into client JS (R-2) | high | low (single-tenant MVP) | Documented; follow-up to add server-side proxy. |
| Future routers want different keys | low | low | `require_api_key` is parameterless — extending to per-router keys is a small refactor (~10 LOC). |

## Estimated Effort

Small. ~150 LOC total across backend + frontend + tests. No human pairing required.
