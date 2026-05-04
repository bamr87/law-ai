# Spec: Native-async HITL quarantine to Postgres

- **ID**: 004-async-quarantine-postgres
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: BL-20260429-02 (BACKLOG.md)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §1 (open-source), §4 (auditability), §7 (HITL).

## 1. Problem & Motivation

`IngestionScout._quarantine_postgres` is implemented as a sync wrapper that calls `asyncio.run()` internally. Because `run_and_commit` is itself an `async` function, this path **always raises `RuntimeError("called from inside event loop")`** in production and falls back to JSONL. Result: low-confidence opinions never reach the `pending_review` Postgres table that the future HITL dashboard (BL-20260429-15) is supposed to query. JSONL is a dev-only escape hatch, not a HITL queue.

Surfaced in [specs/001-ingest-courtlistener-opinions](../001-ingest-courtlistener-opinions) and recorded as **BL-20260429-02**.

## 2. Goals

- G1: When `run_and_commit` runs inside an event loop and Postgres is reachable, low-confidence items land in `pending_review` (no JSONL fallback).
- G2: Keep the JSONL fallback as a true *failure* path — only triggered when the Postgres write actually errors (driver missing, connection refused, schema absent).
- G3: Preserve unit-test ergonomics: tests must still run without `asyncpg` installed against a live database.

## 3. Non-Goals

- NG1: No HITL dashboard UI — that is BL-20260429-15.
- NG2: No new schema. The existing `pending_review` table from `backend/app/db/postgres_migrations/` is reused.
- NG3: No connection pooling/sharing across calls; per-call connect is acceptable for the ingestion volumes in scope.

## 4. User Stories

- As an **ingestion operator**, I want low-confidence opinions to be persisted in Postgres immediately so I can review them later in `psql` (and, eventually, the dashboard) instead of grepping JSONL files.
- As a **test author**, I want to be able to run `pytest` without standing up Postgres or installing `asyncpg`.

## 5. Functional Requirements

- **FR-1**: `IngestionScout._quarantine` MUST be `async def` and MUST be awaited from `run_and_commit` for low-confidence results.
- **FR-2**: `IngestionScout._quarantine_postgres` MUST be `async def` and MUST use the existing event loop (no `asyncio.run` / `asyncio.get_running_loop` gymnastics).
- **FR-3**: When the Postgres write succeeds, the JSONL fallback MUST NOT also be written.
- **FR-4**: When the Postgres write fails for any reason (`ImportError`, `OSError`, `asyncpg.PostgresError`, generic `Exception`), the JSONL fallback MUST be written and the failure MUST be logged via `logger.warning` with the underlying exception class.
- **FR-5**: The `asyncpg` import MUST stay lazy (inside the function) so unit tests do not need the package.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Both Postgres and JSONL paths MUST emit a `provenance.log_agent_call` entry with `output_data.store ∈ {"postgres", "jsonl"}` so audit consumers can tell which sink fired.
- **NFR-PERF-1**: Quarantine write MUST add < 50 ms (p95) at the application layer when Postgres is on localhost (excludes DB round-trip).
- **NFR-COVERAGE-1**: `app/ingestion/scout.py` line coverage MUST stay ≥ 80% (currently 81.60%).
- **NFR-COMPAT-1**: No change to `IngestionScout` public surface (`extract`, `run_and_commit`, ctor) so `scripts/ingest_sample.py` keeps working.

## 7. Data Model Impact

None. Reuses the `pending_review` table defined in `backend/app/db/postgres_migrations/0001_pending_review.sql` (id, source, payload jsonb, confidence, reason, created_at).

## 8. API Surface

No HTTP API changes.

## 9. Agent / Crew Impact

- `IngestionScout` (see [docs/agent-roles.md](../../docs/agent-roles.md)) — internal refactor only; `agent_version` bumps to `0.1.1`.

## 10. Acceptance Criteria

- **AC-1**: Given a low-confidence payload and a stubbed `_quarantine_postgres` that succeeds, when `run_and_commit` is awaited, then no JSONL file is written and the returned summary has `pending=True`, `committed=False`.
- **AC-2**: Given a low-confidence payload and a stubbed `_quarantine_postgres` that raises, when `run_and_commit` is awaited, then exactly one JSONL line is written under `PENDING_REVIEW_DIR` and `provenance.log_agent_call` records `store="jsonl"`.
- **AC-3**: Given a low-confidence payload and a real-but-mocked `asyncpg.connect` (no live Postgres), when `_quarantine_postgres` is awaited, then `conn.execute` is called once with the `INSERT … ON CONFLICT` statement and `conn.close` is awaited even when `execute` raises.
- **AC-4**: `run_and_commit` MUST NOT call `asyncio.run` or `asyncio.get_running_loop` anywhere in the quarantine code path.
- **AC-5**: Existing test `test_low_confidence_routes_to_pending_jsonl` keeps passing without modification beyond switching the monkeypatched method to an `async` callable.

## 11. LegalBench Impact

- Tasks affected: none (refactor only).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: Per-call `asyncpg.connect` adds a TCP handshake per low-confidence opinion. Mitigated by NG3 — pooling deferred until throughput requires it; tracked as a follow-up.

## 13. Out of Scope / Follow-ups

- Connection pooling / shared `asyncpg.Pool`.
- HITL approve/reject endpoints (BL-20260429-15).
- Docker-backed integration test (BL-20260429-01 already tracks this).
