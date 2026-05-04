# Spec: Extend API Authentication to Analysis, Graph, and LSAT Routers

- **ID**: 009-extend-api-auth
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-30
- **Roadmap Epic**: BACKLOG **BL-20260430-08** — "Extend `require_api_key` (or add per-router variants) to gate `/api/analysis`, `/api/graph`, and `/api/lsat`. Today only `/api/agents/*` is protected."
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1, 2, 3, 4, 8, 11.

## 1. Problem & Motivation

Spec 008 shipped a single shared API key for `/api/agents/*` only (NG3 in [specs/008-agent-api-auth/spec.md](../008-agent-api-auth/spec.md)). The remaining surfaces — `/api/analysis` (full IRAC + precedent output), `/api/graph/*` (case + neighborhood data), `/api/lsat/*` (graded responses with answer keys) — are still wide open to anyone who can reach the host. `/health` legitimately stays open as a liveness probe.

Operators deploying beyond localhost (tailnet, LAN, staging) currently get a partial gate: they can hide the BACKLOG and audit feed, but a peer can still grade unlimited LSAT questions, scrape the case graph, or pin the LLM by hammering `/api/analysis`. Constitution §1 ("privacy by default") and §8 ("input validation at every API boundary") require a uniform gate.

This spec generalizes the spec-008 dependency into a **factory** so each router can use its own setting (with fallback to the shared `AGENT_API_KEY`), then mounts it on the three remaining feature routers. It also matches the spec-008 R-3 mitigation: "future specs can introduce per-router settings (`ANALYSIS_API_KEY`, etc.) without rewriting the helper."

Closes **BL-20260430-08**.

## 2. Goals

- G1: Gate `/api/analysis`, `/api/graph/*`, and `/api/lsat/*` behind the same `X-API-Key` mechanism shipped in spec 008.
- G2: Allow operators to set per-router overrides (`ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY`) for fine-grained access control, with the shared `AGENT_API_KEY` as the default fallback.
- G3: Keep local-first dev frictionless: when no key is configured anywhere, all routes stay open (constitution §1 — same posture spec 008 established).
- G4: Update the frontend so the three feature pages keep working when the operator turns the gate on with a single shared key.
- G5: `/health` stays unauthenticated (NG2).

Closes **BL-20260430-08**.

## 3. Non-Goals

- NG1: No per-user identity, accounts, or JWT issuance — single shared key model from spec 008 is preserved.
- NG2: `/health` and `/` (root) routes remain public — they are liveness / discovery probes used by Docker healthchecks and reverse proxies.
- NG3: No rate limiting (still tracked as BL-20260430-09).
- NG4: No moving keys out of the browser bundle (still tracked as BL-20260430-07).
- NG5: No new admin UI to configure or rotate keys; operator sets env vars and restarts.

## 4. User Stories

- As a **maintainer** running the stack on a tailnet, I want to set `AGENT_API_KEY=...` once and have all four feature router groups (`agents`, `analysis`, `graph`, `lsat`) reject unauthenticated peers, so a single env var is the kill-switch for "make this private".
- As an **operator with mixed audiences**, I want to set `LSAT_API_KEY` separately from `AGENT_API_KEY` so that LSAT students can hit `/api/lsat/*` with one key while the ops dashboard uses another, without cross-leakage.
- As a **local developer**, I want `make dev` to keep working with no headers when nothing is configured, so the gate does not change my inner loop.
- As a **frontend user** of `/analysis`, `/graph`, or `/lsat`, I want the page to keep working after the operator enables the gate (because the matching `NEXT_PUBLIC_AGENT_API_KEY` is set), so the protection is invisible.

## 5. Functional Requirements

- **FR-1**: `app.core.security` adds a factory `make_api_key_dep(*setting_names: str)` that returns a FastAPI dependency. The dependency:
  - Reads `settings` for each name in order; the first non-empty value is the "expected" key.
  - When all named settings are empty/None, the dependency is open (returns `None`).
  - Otherwise it requires `X-API-Key` and validates it against the resolved expected key with `secrets.compare_digest`. Missing → `HTTPException(401, "missing api key")`. Mismatch → `HTTPException(401, "invalid api key")`.
- **FR-2**: `require_api_key` (the existing helper) is preserved as `make_api_key_dep("AGENT_API_KEY")` for backwards compatibility — every `/api/agents/*` test added in spec 008 continues to pass with no edits.
- **FR-3**: New settings on `app.core.config.Settings` (all default `None`):
  - `ANALYSIS_API_KEY: str | None`
  - `GRAPH_API_KEY: str | None`
  - `LSAT_API_KEY: str | None`
- **FR-4**: `app/main.py` mounts each feature router with a dedicated dependency:
  - `analysis` → `Depends(make_api_key_dep("ANALYSIS_API_KEY", "AGENT_API_KEY"))`
  - `graph` → `Depends(make_api_key_dep("GRAPH_API_KEY", "AGENT_API_KEY"))`
  - `lsat` → `Depends(make_api_key_dep("LSAT_API_KEY", "AGENT_API_KEY"))`
  - `health` → no dependency (NG2).
- **FR-5**: Startup warning expands: when `AGENT_API_KEY` is unset and `ENVIRONMENT != "development"`, log one WARNING enumerating which router groups are publicly readable (e.g. `"agents,analysis,graph,lsat"`).
- **FR-6**: `frontend/lib/api.ts` is refactored so every cross-cutting `fetch(...)` (including `runAnalysis`, `gradeLsat`, `getJson`) routes through a single `apiFetch(path, init?)` helper that attaches `X-API-Key: ${NEXT_PUBLIC_AGENT_API_KEY}` when the env var is set. The existing `agentFetch` becomes a thin alias of `apiFetch` to preserve call sites.
- **FR-7**: `.env.example` documents the three new per-router keys with the "leave blank to fall back to AGENT_API_KEY" guidance.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: All key comparisons use `secrets.compare_digest`. The factory must not log the key on any path (NFR-SEC-2 from spec 008 carried forward).
- **NFR-SEC-2**: Per-router fallback resolution is constant-time relative to the number of configured settings (≤ 3) — no silent timing channel based on which env var matched.
- **NFR-PERF-1**: Auth dependency adds < 1 ms p95 to each request.
- **NFR-AUDIT-1**: 401 responses still flow through `provenance_middleware`; denied requests appear in the audit JSONL exactly as they do for `/api/agents/*` today.
- **NFR-COVERAGE-1**: Coverage on `app.core.security` ≥ 95 %; overall backend coverage stays ≥ 75 %; frontend stays ≥ 70 %.
- **NFR-COMPAT-1**: Every test that passed before this spec must keep passing without source edits — the default-open posture (no env vars set) is identical to today's behaviour.

## 7. Data Model Impact

None. No Neo4j or Postgres schema changes.

## 8. API Surface

No new routes; existing routes gain dependencies:

```
GET  /health                — UNCHANGED (no auth, NG2)
GET  /                      — UNCHANGED (no auth, NG2)
*    /api/agents/*          — gated by AGENT_API_KEY (unchanged from spec 008)
POST /api/analysis          — NEW gate: ANALYSIS_API_KEY → fallback AGENT_API_KEY
GET  /api/graph/*           — NEW gate: GRAPH_API_KEY    → fallback AGENT_API_KEY
*    /api/lsat/*            — NEW gate: LSAT_API_KEY     → fallback AGENT_API_KEY
```

Error body shape on rejection (matches FastAPI default for `HTTPException`):

```json
{ "detail": "missing api key" }   // or "invalid api key"
```

## 9. Agent / Crew Impact

None. Agents are not invoked by the auth layer; this spec is middleware-shaped. No changes to [docs/agent-roles.md](../../docs/agent-roles.md).

## 10. Acceptance Criteria

- **AC-1**: With every `*_API_KEY` unset, `POST /api/analysis`, `GET /api/graph/stats`, and `GET /api/lsat/questions` all return `200` without an `X-API-Key` header (verifies FR-1 fall-through, FR-4 wiring, NFR-COMPAT-1).
- **AC-2**: With `AGENT_API_KEY="s3cret"` and no per-router override, all three routes (`/api/analysis`, `/api/graph/stats`, `/api/lsat/questions`) return `401 {"detail": "missing api key"}` when no header is sent (verifies fallback resolution).
- **AC-3**: With `AGENT_API_KEY="s3cret"` and `X-API-Key: wrong`, all three routes return `401 {"detail": "invalid api key"}` (verifies mismatch path on the new routers).
- **AC-4**: With `AGENT_API_KEY="s3cret"` and `X-API-Key: s3cret`, all three routes return `200` (verifies happy path on the new routers).
- **AC-5**: With `AGENT_API_KEY=None` and `LSAT_API_KEY="lsat-key"`, `GET /api/lsat/questions` requires `X-API-Key: lsat-key` (other keys rejected) while `/api/analysis` and `/api/graph/stats` remain open (verifies per-router override + isolation, FR-3, FR-4).
- **AC-6**: With `AGENT_API_KEY="shared"` and `LSAT_API_KEY="lsat-key"`, `GET /api/lsat/questions` accepts only `lsat-key` (override wins over fallback); `/api/analysis` accepts `shared` (verifies precedence rules in `make_api_key_dep`).
- **AC-7**: `GET /health` returns `200` regardless of any `*_API_KEY` configuration (verifies NG2).
- **AC-8**: `make_api_key_dep("AGENT_API_KEY")` and `require_api_key` produce identical behaviour across the four spec-008 cases (unset / missing / wrong / correct) — verified by parametrized unit test (verifies FR-2 backwards-compat).
- **AC-9**: When `AGENT_API_KEY` is unset and `ENVIRONMENT="staging"`, the FastAPI app logs one WARNING that names every unprotected router group (`agents`, `analysis`, `graph`, `lsat`) — observed via `caplog` (verifies FR-5).
- **AC-10**: AgentDashboard, AnalysisStudio, KnowledgeGraph, and LsatLab Vitest suites pass with `process.env.NEXT_PUBLIC_AGENT_API_KEY` set; MSW handlers assert `X-API-Key` is forwarded on every gated route (verifies FR-6).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp. This spec is infrastructure / security only.

## 12. Risks & Open Questions

- **R-1**: Existing tests that don't set `AGENT_API_KEY` could break if they pick up a stray env var from the dev shell. Mitigation: add an autouse session-scoped fixture in `backend/tests/conftest.py` that resets all four `*_API_KEY` settings to `None` for the duration of the test session. Per-test `monkeypatch` overrides still work.
- **R-2**: Operators upgrading from spec 008 may be surprised that `AGENT_API_KEY` now also gates `/api/analysis`, `/api/graph/*`, and `/api/lsat/*`. This is an intentional widening (the goal of the spec) but must be called out in the PR description and in `.env.example`.
- **R-3**: Per-router keys could explode in number if every future router adds its own. Mitigation: the factory takes `*setting_names`, so adding new routers reuses the same one-line pattern; document the convention "`<ROUTER>_API_KEY` falls back to `AGENT_API_KEY`" in `.env.example`.

## 13. Out of Scope / Follow-ups

- Move `NEXT_PUBLIC_AGENT_API_KEY` out of the browser bundle (still BL-20260430-07).
- Per-key rate limiting (still BL-20260430-09).
- `docs/security.md` (still BL-20260430-10).
- Per-user authentication (OAuth / JWT) — separate future spec.
- Operator UI for rotating keys without a backend restart.
