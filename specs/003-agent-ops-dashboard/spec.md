# Spec: Agent Operations Dashboard

- **ID**: 003-agent-ops-dashboard
- **Status**: planned
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: User request 2026-04-29 — "build a dashboard to view/monitor and review all of the AI agents work, progress, results, and output"
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1–11.

## 1. Problem & Motivation

Today, every agent run logs JSON via `app.core.provenance` to stdout, but there is no way for a human reviewer to **see** what agents are doing without `docker logs | grep`. Specs and BACKLOG items live in markdown files. There is no single pane of glass that answers "what has the agent stack done lately, what is queued, and what was the result?"

This blocks the HITL loop from working in practice (constitution §1, §11) and makes the self-evolution loop opaque to humans.

Also closes **BL-20260430-02** (TODO in [backend/app/main.py](../../backend/app/main.py): "add registry endpoint").

## 2. Goals

- G1: Persist every provenance event to a queryable store so a UI can tail recent runs.
- G2: Expose four read-only endpoints under `/api/agents/*` that surface registry, runs, BACKLOG, and specs.
- G3: Ship a Next.js page at `/agents` that auto-refreshes and shows all four feeds in one screen.
- G4: Keep all dependencies inside the existing tech stack (constitution §2) — no new database, no new chart lib.

## 3. Non-Goals

- NG1: Authentication / authorization on the dashboard. Local-first MVP; document the gap, file follow-up.
- NG2: Mutation endpoints (no "kill run" or "approve HITL" buttons yet — read-only).
- NG3: Long-term retention. A bounded JSONL ring is enough for MVP.
- NG4: Real-time push (WebSockets). Polling on a 5-second interval is sufficient for MVP.

## 4. User Stories

- As a **reviewer**, I want to see the last 50 agent runs (agent name, latency, confidence, sources count) so I can spot regressions without grepping logs.
- As a **maintainer**, I want to see the BACKLOG (Open / Claimed / Done counts + top items) so I can pick the next `/evolve` cycle without opening the markdown file.
- As a **stakeholder**, I want to see what agents are registered and which specs are in flight so I can answer "what is the AI doing for us this week?"

## 5. Functional Requirements

- **FR-1**: New module `app.core.audit_store` exposes `record(event: dict) -> None` (append-only) and `tail(limit: int) -> list[dict]`. Backed by a single JSONL file at `LawGraph_AUDIT_PATH` (defaults to `backend/.audit/provenance.jsonl`). File location is settings-driven so tests use a tmp path.
- **FR-2**: `ProvenanceLogger.log_agent_call`, `log_request`, and `log_graph_query` additionally call `audit_store.record(...)`. Existing stdout logging is preserved.
- **FR-3**: `GET /api/agents` returns `{"agents": [{"name": str, "module": str}]}` from `AGENT_REGISTRY`.
- **FR-4**: `GET /api/agents/runs?limit=N` (1 ≤ N ≤ 200, default 50) returns the most recent N events from the audit store, newest first.
- **FR-5**: `GET /api/agents/backlog` parses [BACKLOG.md](../../BACKLOG.md) and returns `{"open": [...], "claimed": [...], "done": [...], "counts": {...}}` where each item is `{"id", "kind", "severity", "title"}`.
- **FR-6**: `GET /api/agents/specs` lists every directory under `specs/` (excluding `_template`) and reports `{"id", "status"}` parsed from each `spec.md` `Status:` line.
- **FR-7**: New Next.js route `/agents` renders the dashboard with four panels (Registry, Recent Runs, Backlog, Specs) and polls every 5s via the existing `lib/api.ts` client.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: `GET /api/agents/runs?limit=50` returns in < 100 ms cold (reads at most 50 lines off the tail of a JSONL file).
- **NFR-AUDIT-1**: Persistence to the audit store happens *after* stdout logging; a write failure on the store must NOT crash the request — log a warning and continue.
- **NFR-IDEMPOTENT-1**: Backlog and specs parsers are pure functions of file content — same input → same output.
- **NFR-SEC-1**: All four endpoints are read-only. No path traversal — the BACKLOG / specs paths are computed from `settings`, never from the request.
- **NFR-COVERAGE-1**: Backend coverage stays ≥ 75%. Frontend coverage stays ≥ 70%.

## 7. Data Model Impact

- No Neo4j changes.
- One new on-disk artifact: `backend/.audit/provenance.jsonl`. Bounded by an in-process `MAX_AUDIT_LINES` cap (default 10_000) — when exceeded, the file is truncated to the last 5_000 lines (simple ring rotation, no extra dependency).

## 8. API Surface

```
GET /api/agents               -> {"agents": [{"name", "module"}]}
GET /api/agents/runs?limit=N  -> {"runs": [<event>, ...], "count": N}
GET /api/agents/backlog       -> {"counts": {...}, "open": [...], "claimed": [...], "done": [...]}
GET /api/agents/specs         -> {"specs": [{"id", "status"}]}
```

All responses are JSON; no auth.

## 9. Agent / Crew Impact

- `IngestionScout`, `LegalAnalyst`, `PrecedentHunter` — no behavioral change. They already call `provenance.*`; FR-2 makes those calls visible.
- New "operator" persona in [docs/agent-roles.md](../../docs/agent-roles.md) is **not** added — this spec ships infra, not a new agent.

## 10. Acceptance Criteria

- **AC-1**: After issuing one analysis request, `GET /api/agents/runs?limit=10` returns ≥ 1 event whose `agent` matches the called crew (verifies FR-1, FR-2, FR-4).
- **AC-2**: `GET /api/agents/backlog` returns counts where `open + claimed + done == 18` against the current [BACKLOG.md](../../BACKLOG.md) (verifies FR-5; specific number updates as BACKLOG grows — test pins on the ratio, not the absolute, by reading the file).
- **AC-3**: `GET /api/agents/specs` includes both `001-ingest-courtlistener-opinions` and `002-resolve-citations-to-cases` with parsed `status`.
- **AC-4**: `GET /api/agents` returns at least the three currently-registered agents.
- **AC-5**: `audit_store.record` failure (e.g. read-only filesystem) does NOT propagate; the calling agent run still succeeds (verifies NFR-AUDIT-1 with a monkey-patched failing writer).
- **AC-6**: Loading `/agents` in the frontend renders all four panel headings; the `Registry` panel renders one card per agent returned by the mocked API (verifies FR-7 via vitest + MSW).
- **AC-7**: Audit JSONL grows past `MAX_AUDIT_LINES` triggers truncation to the configured `KEEP_AUDIT_LINES` count, with no event loss for the most recent slice (verifies the ring rotation).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp. This spec touches infrastructure only.

## 12. Risks & Open Questions

- **R-1**: JSONL is not transactional. Concurrent writes could interleave bytes. Mitigation: use `open(..., "a", buffering=1)` and write `json.dumps(...) + "\n"` atomically per call (POSIX append is atomic for writes ≤ `PIPE_BUF`). Document the small-event constraint; revisit when events exceed 4 KB.
- **R-2**: BACKLOG.md format drift could break the parser. Mitigation: parser uses the same regex as [scripts/backlog_lint.py](../../scripts/backlog_lint.py) so any drift is caught by the existing CI gate.

## 13. Out of Scope / Follow-ups

- AuthN/Z on the dashboard.
- WebSocket push.
- Trace drill-down view (single run with full input/output).
- Approve / reject HITL items from the UI.
