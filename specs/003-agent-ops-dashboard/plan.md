# Plan: 003 — Agent Operations Dashboard

## Approach

Three layers, each independently testable:

1. **Persistence layer** — `app/core/audit_store.py`. Pure JSONL append-and-tail, no DB.
2. **Read API** — `app/api/agents.py`, four routes, all read-only, all hermetic-testable with `tmp_path` and `monkeypatch`.
3. **UI** — single Next.js client component `components/AgentDashboard.tsx` that polls the four endpoints; thin server-component shell at `app/agents/page.tsx`.

## File Layout

```
backend/app/core/audit_store.py        (new, ~80 LOC)
backend/app/core/provenance.py         (edit — tee to audit_store)
backend/app/core/config.py             (edit — add AUDIT_PATH + caps)
backend/app/api/agents.py              (new, ~130 LOC)
backend/app/main.py                    (edit — mount router; remove stale TODO)
backend/tests/core/test_audit_store.py (new)
backend/tests/api/test_agents.py       (new)

frontend/app/agents/page.tsx           (new, server shell)
frontend/components/AgentDashboard.tsx (new, client)
frontend/lib/api.ts                    (edit — add fetchers)
frontend/__tests__/components/AgentDashboard.test.tsx (new, MSW-mocked)
```

## Why These Choices

- **JSONL over SQLite**: zero new dependencies, trivially `tail`-able, fits the "local-first, auditable" mandate (constitution §1, §4). The lint-style ring rotation keeps disk bounded without invoking logrotate.
- **Polling over WebSockets**: 5 s is fine for a HITL review surface; WebSockets would be premature optimization plus a new ASGI dependency.
- **Reuse `BACKLOG.md` regex from `scripts/backlog_lint.py`**: single source of truth for the format; if the lint regex changes, the parser is updated in lockstep.
- **Read-only API**: no auth needed for an MVP that only reflects state; mutation endpoints would force the auth conversation early. Logged as NG1 + follow-up.

## Cross-Cutting Concerns

- **Provenance (constitution §4)**: every API call still flows through the existing `provenance_middleware`, so dashboard usage is itself auditable.
- **HITL (constitution §1, §11)**: no behavioral change; HITL gates remain in the ingestion path.
- **Tests (§3)**: ≥ 75 % backend, ≥ 70 % frontend. New code is small and pure → easy to hit.

## Risk Mitigations

- Concurrent JSONL appends (R-1): write whole-line `json.dumps(...) + "\n"`; document the 4 KB POSIX append-atomicity constraint in the module docstring.
- BACKLOG drift (R-2): import the canonical regex from `scripts.backlog_lint` directly so divergence is impossible.
