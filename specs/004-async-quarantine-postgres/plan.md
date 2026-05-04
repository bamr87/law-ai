# Plan: 004 — Native-async HITL quarantine to Postgres

## Approach

Replace the sync-over-async hack in `IngestionScout._quarantine_postgres` with a true coroutine, and make `_quarantine` itself `async` so it can be awaited from the already-async `run_and_commit`. The lazy `import asyncpg` stays, but instead of calling `asyncio.run(_write())` we just `await conn.execute(...)`.

```text
run_and_commit (async)
  └── if low-confidence:
       └── await self._quarantine(result, payload)  # async
             ├── try:  await self._quarantine_postgres(...)  # async, uses asyncpg
             │         └── provenance.log_agent_call(store="postgres")
             └── except Exception as exc:
                       logger.warning("postgres failed (%s); using JSONL", type(exc).__name__)
                       self._quarantine_jsonl(...)            # sync fs write
                       provenance.log_agent_call(store="jsonl")
```

## Files touched

| File | Change |
|------|--------|
| `backend/app/ingestion/scout.py` | Make `_quarantine` + `_quarantine_postgres` `async`; split JSONL into `_quarantine_jsonl`; bump `agent_version`. |
| `backend/tests/ingestion/test_scout.py` | Update existing JSONL test (monkeypatch with `AsyncMock`); add 2 new tests for postgres-success and asyncpg-mocked paths. |
| `BACKLOG.md` | Move BL-20260429-02 from `## Open` → `## Done`; append any follow-ups discovered. |
| `specs/004-async-quarantine-postgres/{spec,plan,tasks}.md` | This spec. |

## Test strategy

- **AC-1 (postgres-only path)**: monkeypatch `IngestionScout._quarantine_postgres` with an `AsyncMock` that returns `None`; assert no JSONL file produced and summary shape correct.
- **AC-2 (jsonl fallback)**: monkeypatch `_quarantine_postgres` with an `AsyncMock(side_effect=RuntimeError)`; assert exactly one JSONL line written under `PENDING_REVIEW_DIR`.
- **AC-3 (asyncpg call shape)**: build a fake module exposing `connect` that returns a `MagicMock` with `execute`/`close` as `AsyncMock`s; install via `monkeypatch.setitem(sys.modules, "asyncpg", fake)`; await `_quarantine_postgres` directly and assert `execute.call_args[0][0]` contains `"INSERT INTO pending_review"` and `close` was awaited.
- **AC-4**: ripgrep regression — `assert "asyncio.run" not in source` and `"get_running_loop" not in source` for the touched module.
- **AC-5**: keep existing `test_low_confidence_routes_to_pending_jsonl` passing after switching the monkeypatched method to an async function.

## Rollback

Single file change in scout.py; revert via `git checkout backend/app/ingestion/scout.py` if pytest regresses.

## Out of scope (mirrored to BACKLOG)

- Connection pooling.
- Real Postgres docker-backed integration test (BL-20260429-01 already tracks).
