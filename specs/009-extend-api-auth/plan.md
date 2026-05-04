# Plan: 009 — Extend API Authentication

## Approach

Three small, surgical layers — each preserves spec 008's posture and re-uses its primitives:

1. **Generalize the auth helper** — `app/core/security.py` adds `make_api_key_dep(*setting_names)` returning a fresh `Depends`-able callable. The existing `require_api_key` collapses to one line: `require_api_key = make_api_key_dep("AGENT_API_KEY")`. Behaviour for spec 008 callers is byte-identical.
2. **Mount per-router** — `app/main.py` adds three new dependencies, one per feature router. Each router resolves its own setting first and falls back to `AGENT_API_KEY` when its override is empty.
3. **Frontend single-helper refactor** — `frontend/lib/api.ts` consolidates the three `fetch(...)` styles (raw POST, raw GET, `getJson`, `agentFetch`) onto one `apiFetch(path, init?)`. The function attaches `X-API-Key` from `NEXT_PUBLIC_AGENT_API_KEY` whenever it is set. `agentFetch` becomes a one-line alias to keep call sites unchanged.

## File Layout

```
backend/app/core/security.py             (edit — add make_api_key_dep; require_api_key stays)
backend/app/core/config.py               (edit — add three per-router settings)
backend/app/main.py                      (edit — three new include_router deps + expanded warning)
backend/tests/conftest.py                (edit — autouse fixture neutralises *_API_KEY env)
backend/tests/core/test_security.py      (edit — add factory cases incl. precedence + AC-8)
backend/tests/api/test_analysis.py       (edit — +AC-1..AC-4 cases)
backend/tests/api/test_graph.py          (edit — +AC-1..AC-4 cases)
backend/tests/api/test_lsat.py           (edit — +AC-1..AC-6 cases incl. override + isolation)

frontend/lib/api.ts                      (edit — apiFetch consolidates fetch + getJson + agentFetch)
frontend/__tests__/components/AnalysisStudio.test.tsx   (edit — assert X-API-Key when env set)
frontend/__tests__/components/KnowledgeGraph.test.tsx   (edit — same)
frontend/__tests__/components/AgentDashboard.test.tsx   (existing — unchanged behaviour, still asserts header)

.env.example                             (edit — add ANALYSIS/GRAPH/LSAT keys)
```

## Why These Choices

- **Factory over multiple bespoke dependencies**: keeps the auth surface to one helper. Adding a future router is one new `include_router(...)` line + (optionally) one new setting.
- **Override-then-fallback resolution** (FR-1: first non-empty wins): operators get the dual model "set one key, get one gate" *and* "set per-router keys, get isolation" with no extra code. Matches spec 008 R-3 explicitly.
- **`require_api_key` preserved as alias**: every spec-008 test passes with no edits — protects NFR-COMPAT-1 and the audit gate.
- **Single `apiFetch` on the frontend**: today there are four flavours of `fetch(...)` in `lib/api.ts`. Folding them into one removes accidental drift if a future feature wires a new endpoint and forgets the header.
- **Autouse `_reset_api_keys` fixture in `conftest.py`**: hermetic — protects every existing test from a developer's stray `.env` and from the new gates.

## Provenance & Audit Hook-up

No new provenance events. The existing `provenance_middleware` (spec 003) already tees every request — including 401s — into `audit_store`. Operators continue to see denied requests in `/api/agents/runs`. The `X-API-Key` header is never read by the provenance layer (NFR-SEC-2 carried over from spec 008).

## HITL Gates

None. This spec does not change any HITL path; the existing ingestion-quarantine gate (spec 004) and the analysis HITL flag (spec 007) remain untouched.

## Test Strategy

- **Unit (`test_security.py`)**: extend with parametrized cases for `make_api_key_dep`:
  - Single name, all four spec-008 branches (proves FR-2 / AC-8).
  - Two names with override set → expected key is the override (AC-6).
  - Two names with only fallback set → expected key is the fallback (AC-2).
  - All names empty → open (AC-1).
- **API (`test_analysis.py`, `test_graph.py`, `test_lsat.py`)**: add a `with_shared_key` fixture using `monkeypatch.setattr(settings, "AGENT_API_KEY", ...)`; reuse the spec-008 `_isolate_audit` pattern. Cover AC-1..AC-4 in each module; AC-5 + AC-6 + isolation in `test_lsat.py`.
- **Health (`test_health.py`)**: extend (or add) one test that proves AC-7 — `GET /health` returns 200 even when every key is set.
- **Startup warning (AC-9)**: extend the spec-008 warning test to assert the message lists all four router groups.
- **Frontend (`AnalysisStudio.test.tsx`, `KnowledgeGraph.test.tsx`)**: add MSW handlers that capture `request.headers.get('x-api-key')` and assert it equals `'s3cret'` when `vi.stubEnv('NEXT_PUBLIC_AGENT_API_KEY', 's3cret')` is active. Keep the env-unset case to prove no header is sent.
- **No LegalBench delta needed** (no reasoning code touched).

## Rollout

- Local dev: no action — keys unset → behaviour unchanged.
- Staging / tailnet: operator sets `AGENT_API_KEY` (and optionally per-router overrides) in backend `.env`, sets `NEXT_PUBLIC_AGENT_API_KEY` in frontend `.env`, restarts. `docker compose up --build` picks both up.
- No backfill, no migration, no flag beyond the keys themselves.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Stray dev `.env` leaks an `AGENT_API_KEY` into test runs | med | high (suite goes red) | Autouse `_reset_api_keys` fixture in `backend/tests/conftest.py`. |
| Operator confusion: "I only set `AGENT_API_KEY` for the dashboard, why is `/api/analysis` 401?" | med | low | Explicit callout in `.env.example` + PR description; documented in spec §12 R-2. |
| Frontend page breaks because we forgot to thread the header through one call | low | med | Single `apiFetch` helper used by **every** outgoing call; vitest assertions on each gated suite. |

## Estimated Effort

Small. ~250 LOC total across backend + frontend + tests. No human pairing required.
