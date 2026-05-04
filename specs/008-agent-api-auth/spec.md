# Spec: Agent API Authentication

- **ID**: 008-agent-api-auth
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-30
- **Roadmap Epic**: BACKLOG **BL-20260429-13** — "Add authn/z to `/api/agents/*` routes before the dashboard is exposed beyond localhost."
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1, 2, 3, 4, 8, 11.

## 1. Problem & Motivation

Spec 003 shipped the agent ops dashboard read-only and intentionally deferred auth (NG1 in [specs/003-agent-ops-dashboard/spec.md](../003-agent-ops-dashboard/spec.md)). The four `/api/agents/*` routes leak provenance events (`/runs`), the BACKLOG, and the registry to anyone who can reach the host.

Today this is fine because the only deployment is `localhost`. The next deployment target (any compose stack on a developer's LAN, a tailnet, or a cloud staging box) will expose the dashboard publicly. Constitution §1 ("privacy by default") and §8 ("input validation at every API boundary") require we close this gap before that happens, and BL-20260429-13 is the highest-severity Open item in [BACKLOG.md](../../BACKLOG.md).

## 2. Goals

- G1: Gate every `/api/agents/*` route behind a single shared API key that the operator configures in `.env`.
- G2: Keep local-first dev DX painless — when no key is configured the routes stay open (with a loud startup warning) so `make dev` keeps working out of the box.
- G3: Wire the existing `AgentDashboard` UI to forward the configured key so the dashboard keeps rendering after the gate is enabled.
- G4: Add a reusable `require_api_key` FastAPI dependency in `app.core.security` that future specs can apply to other routers (analysis, graph, lsat) without rewriting the auth logic.

Closes **BL-20260429-13**.

## 3. Non-Goals

- NG1: No new user model, no per-user accounts, no JWT issuance — single shared key only. A multi-user identity layer is a future spec.
- NG2: No rate limiting or abuse detection. Auth only.
- NG3: Auth is **not** applied to `/api/analysis`, `/api/graph`, `/api/lsat`, or `/health` in this spec — gating those needs separate UX consideration. Tracked as a follow-up.
- NG4: No client-side key rotation flow or admin UI. Operator restarts the backend with a new `.env` value.

## 4. User Stories

- As a **maintainer** running the stack on a tailnet, I want to set `AGENT_API_KEY=...` in `.env` and have all `/api/agents/*` routes reject requests without that key, so unauthenticated peers cannot read the BACKLOG or audit feed.
- As a **dashboard user**, I want the `/agents` page to keep working after the gate is enabled (because I configured the matching key in the frontend env), so the protection is invisible to me.
- As a **local developer**, I want `make dev` to keep working with no auth headers when I have not set `AGENT_API_KEY`, so the privacy gate does not get in the way of inner-loop work.
- As a **reviewer**, I want a 401 on a missing/wrong key and a 200 on a correct key, with a clear error body, so I can verify the gate without reading source.

## 5. Functional Requirements

- **FR-1**: New module `app.core.security` exposes a FastAPI dependency `require_api_key(x_api_key: str | None = Header(None)) -> None` that:
  - Returns `None` (allow) when `settings.AGENT_API_KEY` is `None` or empty.
  - Raises `HTTPException(401, {"detail": "missing api key"})` when the setting is configured but the header is absent.
  - Raises `HTTPException(401, {"detail": "invalid api key"})` when the header is present but does not equal the setting (compared with `secrets.compare_digest` to avoid timing leaks).
- **FR-2**: New setting `AGENT_API_KEY: str | None = None` is added to `app.core.config.Settings` (read from env `AGENT_API_KEY`).
- **FR-3**: `app.api.agents.router` mounts the dependency once via `dependencies=[Depends(require_api_key)]` on `app.include_router(...)` in `app.main`. Every existing `/api/agents`, `/api/agents/runs`, `/api/agents/backlog`, `/api/agents/specs` request now flows through the gate.
- **FR-4**: At startup (`lifespan`), if `AGENT_API_KEY` is unset and `ENVIRONMENT != "development"`, log one `WARNING` line: `"AGENT_API_KEY not set — /api/agents/* is publicly readable"`.
- **FR-5**: `frontend/lib/api.ts` reads `process.env.NEXT_PUBLIC_AGENT_API_KEY` and, when non-empty, attaches `X-API-Key: <value>` to every `/api/agents/*` request. Other endpoints are unaffected.
- **FR-6**: `.env.example` documents both `AGENT_API_KEY` (backend) and `NEXT_PUBLIC_AGENT_API_KEY` (frontend), including the "leave blank for local dev" guidance.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: Key comparison uses `secrets.compare_digest` (constant-time) — never `==`.
- **NFR-SEC-2**: The configured key is **never** logged. The startup warning (FR-4) only states whether one is configured. Provenance and audit events do not include the header value.
- **NFR-PERF-1**: Auth dependency adds < 1 ms p95 to each request (single string compare; no DB / no I/O).
- **NFR-AUDIT-1**: 401 responses still flow through `provenance_middleware` so denied requests are visible in the audit JSONL via the existing `log_request` path.
- **NFR-COVERAGE-1**: Backend coverage on `app.core.security` ≥ 95 %; overall backend coverage stays ≥ 75 %. Frontend coverage stays ≥ 70 %.

## 7. Data Model Impact

None. No Neo4j or Postgres schema changes. No new on-disk files.

## 8. API Surface

No new routes; existing routes gain a dependency:

```
GET /api/agents               — now requires X-API-Key when AGENT_API_KEY is set
GET /api/agents/runs?limit=N  — same
GET /api/agents/backlog       — same
GET /api/agents/specs         — same
```

Error body shape on rejection (matches FastAPI default for `HTTPException`):

```json
{ "detail": "missing api key" }   // or "invalid api key"
```

## 9. Agent / Crew Impact

None. Agents are not invoked by these endpoints; this spec is purely middleware-shaped. No changes to [docs/agent-roles.md](../../docs/agent-roles.md).

## 10. Acceptance Criteria

- **AC-1**: With `AGENT_API_KEY=""` (default), `GET /api/agents` returns `200` and the existing payload, with no `X-API-Key` header in the request (verifies FR-1 fall-through and FR-3 wiring).
- **AC-2**: With `AGENT_API_KEY="s3cret"` and no header, `GET /api/agents` returns `401` with `{"detail": "missing api key"}` (verifies FR-1 missing-key path).
- **AC-3**: With `AGENT_API_KEY="s3cret"` and `X-API-Key: wrong`, `GET /api/agents/runs` returns `401` with `{"detail": "invalid api key"}` (verifies FR-1 mismatch path + NFR-SEC-1).
- **AC-4**: With `AGENT_API_KEY="s3cret"` and `X-API-Key: s3cret`, all four `/api/agents/*` routes return `200` (verifies FR-3 across the whole router).
- **AC-5**: A unit test on `require_api_key` confirms it uses `secrets.compare_digest` (asserted via `monkeypatch` of the symbol, verifying NFR-SEC-1).
- **AC-6**: AgentDashboard vitest suite passes when `process.env.NEXT_PUBLIC_AGENT_API_KEY` is set — MSW handlers assert that the `X-API-Key` header is present and equal to the configured value (verifies FR-5).
- **AC-7**: When `AGENT_API_KEY` is unset and `ENVIRONMENT="staging"`, the FastAPI app logs the FR-4 warning exactly once on startup (verifies FR-4 — observed via `caplog`).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp. This spec is infrastructure / security only.

## 12. Risks & Open Questions

- **R-1**: Operators who upgrade may have a key set in backend `.env` but forget to set `NEXT_PUBLIC_AGENT_API_KEY` in the frontend, breaking the dashboard. Mitigation: surface a clear panel-level error ("401 — set NEXT_PUBLIC_AGENT_API_KEY") via the existing per-panel error handling in `AgentDashboard`. Documented in the README/`.env.example`.
- **R-2**: `NEXT_PUBLIC_*` env vars are bundled into the client JS, so the key is **not** secret from a user who can load the page. This is an explicit trade-off for an MVP single-tenant operator key. Documented in the spec; tracked as a follow-up to introduce a Next.js server-side proxy that holds the key out of the browser bundle.
- **R-3**: A future spec gating `/api/analysis`, `/api/graph`, and `/api/lsat` with the same key would re-couple unrelated surfaces. Mitigation: `require_api_key` is a generic FastAPI dependency keyed on a single setting; future specs can introduce per-router settings (`ANALYSIS_API_KEY`, etc.) without rewriting the helper.

## 13. Out of Scope / Follow-ups

- Per-user authentication (OAuth / JWT).
- Server-side proxy in Next.js so the key never enters the browser bundle.
- Extending the gate to `/api/analysis`, `/api/graph`, `/api/lsat`.
- Rate limiting / abuse detection.
- Operator UI for rotating the key without a backend restart.
