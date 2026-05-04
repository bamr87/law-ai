# Tasks: 004 — Native-async HITL quarantine to Postgres

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — Make `_quarantine` and `_quarantine_postgres` truly async

- **Refs**: FR-1, FR-2, FR-3, FR-4, FR-5, NFR-PERF-1, NFR-COMPAT-1, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/ingestion/scout.py` (edit)
- **Steps**:
  1. Convert `_quarantine` to `async def` and `await self._quarantine_postgres(...)`. On exception, call new sync helper `_quarantine_jsonl(...)` and `logger.warning("pending_review postgres write failed (%s); using JSONL", type(exc).__name__)`.
  2. Convert `_quarantine_postgres` to `async def`. Body: lazy `import asyncpg`, `await asyncpg.connect(dsn)`, `await conn.execute(...)`, `await conn.close()` in `finally`. Remove all `asyncio.run` / `get_running_loop` calls.
  3. Update `run_and_commit` to `await self._quarantine(result, payload)`.
  4. Bump `IngestionScout.agent_version` from `"0.1.0"` to `"0.1.1"`.
- **Verify**:
  - `grep -n "asyncio.run\|get_running_loop" backend/app/ingestion/scout.py` returns no matches.
  - `mypy app/ingestion/scout.py --strict` clean.

## T-002 — Split JSONL fallback + provenance store tag

- **Refs**: FR-3, FR-4, NFR-AUDIT-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/ingestion/scout.py` (edit)
- **Steps**:
  1. Extract the JSONL write block (currently inside `_quarantine`) into `_quarantine_jsonl(self, result, payload)` (sync, fs only).
  2. After Postgres write, emit `provenance.log_agent_call(... output_data={"pending": True, "store": "postgres"} ...)`.
  3. Keep the existing JSONL-side `provenance.log_agent_call` (already sets `store="jsonl"`).
- **Verify**: covered by tests in T-003.

## T-003 — Tests: postgres-only, asyncpg call shape, no-asyncio-run regression

- **Refs**: AC-1, AC-2, AC-3, AC-4, AC-5, NFR-COVERAGE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/ingestion/test_scout.py` (edit)
- **Steps**:
  1. Update `test_low_confidence_routes_to_pending_jsonl` to monkeypatch `_quarantine_postgres` with an `AsyncMock(side_effect=RuntimeError("no pg"))` so the new async signature works (AC-5 / AC-2).
  2. Add `test_low_confidence_routes_to_postgres_when_available`: monkeypatch `_quarantine_postgres` with `AsyncMock(return_value=None)`; await `run_and_commit`; assert summary shape and that **no** JSONL file was created (AC-1).
  3. Add `test_quarantine_postgres_uses_asyncpg_correctly`: install a fake `asyncpg` module via `monkeypatch.setitem(sys.modules, "asyncpg", fake)` whose `connect` returns a `MagicMock` with `execute=AsyncMock()`, `close=AsyncMock()`; await `scout._quarantine_postgres(result, {})`; assert SQL contains `INSERT INTO pending_review` and `close` was awaited even when `execute` raises (AC-3).
  4. Add `test_no_asyncio_run_in_quarantine_path`: read `app/ingestion/scout.py` source and assert neither `"asyncio.run("` nor `"get_running_loop"` substrings are present (AC-4).
- **Verify**:
  - `cd backend && pytest tests/ingestion/test_scout.py -q` all pass.
  - `cd backend && pytest --cov=app --cov-fail-under=75` ≥ 75 %.

## T-004 — Backlog hygiene

- **Refs**: NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit)
- **Steps**:
  1. Move **BL-20260429-02** from `## Open` to `## Done` with one-line outcome and link to spec 004.
  2. Append any new follow-ups discovered (mirror items from `## Follow-ups Discovered` below).
- **Verify**: `python3 scripts/backlog_lint.py` exit 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make test` green (backend ≥ 75 % coverage).
- BL-20260429-02 moved to `## Done` in BACKLOG.md.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- **BL-20260429-17** — *infra, low* — Introduce a shared `asyncpg.Pool` in `app.db.postgres` so HITL writes (and future routes) reuse connections instead of doing per-call `connect`/`close`. _Surfaced in:_ specs/004-async-quarantine-postgres NFR-PERF-1.
