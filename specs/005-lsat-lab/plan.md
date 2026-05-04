# Plan: 005-lsat-lab

## Architecture

- New backend package `backend/app/lsat/` with `__init__.py`, `bank.py` (loader + Pydantic models), `data/lr_bank.json` (seed bank).
- New router `backend/app/api/lsat.py` mounted at `/api/lsat` from `app.main`.
- Frontend page `frontend/app/lsat/page.tsx` (client component) + `frontend/lib/api.ts` extended with `fetchLsatQuestion`, `gradeLsat`, `fetchLsatStats`.

## Files Touched

| File | Change |
|------|--------|
| `backend/app/lsat/__init__.py` | new (empty) |
| `backend/app/lsat/bank.py` | new — Pydantic models + `load_bank()` |
| `backend/app/lsat/data/lr_bank.json` | new — 5 seed LR items |
| `backend/app/api/lsat.py` | new — 3 routes |
| `backend/app/main.py` | mount router |
| `backend/tests/api/test_lsat.py` | new — covers AC-1..AC-5 |
| `frontend/lib/api.ts` | add LSAT helpers + types |
| `frontend/app/lsat/page.tsx` | new — practice flow |
| `BACKLOG.md` | append BL-20260429-18..20 |

## Test Strategy

- Backend: pytest async client tests for each endpoint, plus a unit test that the bank parses and every item satisfies AC-5.
- Frontend: smoke render only this cycle (no network test) — covered by the existing dashboard test infra; `/lsat` smoke test deferred to a follow-up if vitest infra grows.
