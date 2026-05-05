# Operator Runbook — LexGraph Revert (canonical name remains LawGraph AI)

> Companion to [ADR 0002](adr/0002-rebrand-lawgraph-ai.md) and [specs/012-rebrand-lawgraph-ai/](../specs/012-rebrand-lawgraph-ai/). Targets operators who pulled the half-rebranded intermediate state and need a clean upgrade path back to a working LawGraph stack.

## TL;DR

The brand is — and always has been at the code layer — **LawGraph AI**. A short-lived attempt to rename the on-disk Python package directory to `backend/lexgraph/` left the rest of the codebase (every import, settings module, Celery app, ASGI ref, Postgres role) untouched and broke the backend. ADR 0002 reverts that directory rename and re-aligns the docs/prompts/specs to "LawGraph AI". There are **no env-var deltas** for any operator running off the original `.env.example`.

## Audience & paths

| Situation                                                          | Path                                               |
|--------------------------------------------------------------------|----------------------------------------------------|
| Greenfield install (no existing volumes / databases)               | [§1 Greenfield](#1-greenfield)                     |
| You pulled a commit that contained `backend/lexgraph/` and want to upgrade | [§2 Upgrade from the broken state](#2-upgrade-from-the-broken-state) |
| You have an existing working LawGraph stack and never saw `lexgraph/` | No action required. `git pull` and continue.       |

## 1. Greenfield

```bash
git pull
cp .env.example .env       # only if you don't already have a .env
make dev                    # docker compose up --build
```

Verify:

```bash
make local-ai-health        # /api/agents/health/local-ai → all green
curl -s http://localhost:8000/health | jq
docker compose logs backend | grep "Starting development server"
```

## 2. Upgrade from the broken state

If your working tree contained `backend/lexgraph/` and the backend was failing to boot with `ModuleNotFoundError: No module named 'lawgraph'`, follow these steps.

### Step 0 — Snapshot (only if you have data you care about)

```bash
docker compose exec postgres pg_dump -U lawgraph -d lawgraph -Fc -f /tmp/lawgraph.dump
docker compose cp postgres:/tmp/lawgraph.dump ./backups/
docker compose exec neo4j neo4j-admin database dump --to-path=/backups neo4j
cp -R backend/.audit ./backups/audit-$(date +%Y%m%d).bak
```

### Step 1 — Pull and stop

```bash
git pull
docker compose down       # do NOT pass -v; that would delete volumes
```

### Step 2 — Confirm the directory is back to `backend/lawgraph/`

`git pull` of the revert commit should leave you with `backend/lawgraph/` and no `backend/lexgraph/`. Verify:

```bash
ls backend/ | grep -E '^l(aw|ex)graph$'
# expected: lawgraph
```

If you see `lexgraph` instead, you have local uncommitted work conflicting with the revert. Stash it (`git stash`), re-pull, then reapply manually.

### Step 3 — Clean stale `.pyc` files

The half-rebranded state cached `lexgraph` byte-code that will continue to import (and import wrong) until cleared:

```bash
find backend -type d -name __pycache__ -exec rm -rf {} +
find backend -type f -name '*.pyc' -delete
```

### Step 4 — Rebuild containers

```bash
docker compose build backend worker
docker compose up -d
```

### Step 5 — Verify

```bash
docker compose ps                              # all services Up (healthy)
curl -s http://localhost:8000/health | jq      # status: ok
make local-ai-health                           # local-ai checks pass
```

Browser at `http://localhost:3000` — title bar reads "LawGraph AI"; nav loads `/agents`, `/analysis`, `/graph`, `/lsat` without console errors.

## What did NOT change

These deliberately stayed the same — no operator action required:

| Surface                       | Value           | Notes |
|-------------------------------|-----------------|-------|
| Postgres role                 | `lawgraph`      | Was never going to change. |
| Postgres database name        | `lawgraph`      | Was never going to change. |
| Postgres password (dev)       | `lawgraph-dev`  | Override via `POSTGRES_PASSWORD` for prod. |
| Neo4j password (dev)          | `lawgraph-dev`  | Override via `NEO4J_PASSWORD` for prod. |
| Phoenix project name          | `lawgraph`      | Set via `PHOENIX_PROJECT_NAME`. |
| Celery app name               | `lawgraph`      | `Celery("lawgraph")` in [backend/lawgraph/celery.py](../backend/lawgraph/celery.py). |
| `DJANGO_SETTINGS_MODULE` default | `lawgraph.settings.dev` | Override per env. |
| GitHub repo slug              | `law-ai`        | [specs/012 NG-1](../specs/012-rebrand-lawgraph-ai/spec.md). |

## Rollback

If anything goes wrong:

```bash
docker compose down
git checkout <pre-revert-sha>
docker compose up -d
```

Postgres and Neo4j volumes are untouched by the revert; data on the original `lawgraph` role/db is safe.

## Verification checklist

- [ ] `docker compose ps` — all services `Up (healthy)`.
- [ ] `curl -s http://localhost:8000/health | jq .status` → `"ok"`.
- [ ] `curl -s http://localhost:8000/api/agents/health/local-ai` → all `reachable: true`.
- [ ] Browser at `http://localhost:3000` — title reads "LawGraph AI".
- [ ] `python scripts/spec_validator.py` exits 0.
- [ ] `python scripts/backlog_lint.py` exits 0.
- [ ] `docker compose logs backend | grep -i "celery\|daphne" | tail -20` — workers and ASGI server reported ready.

## Related docs

- [ADR 0002](adr/0002-rebrand-lawgraph-ai.md) — decision rationale.
- [specs/012-rebrand-lawgraph-ai/](../specs/012-rebrand-lawgraph-ai/) — full spec/plan/tasks for the revert.
- [docs/security.md](security.md) — token model (unchanged by the revert).
- [docs/local-ai.md](local-ai.md) — service ports, Phoenix project name semantics.
