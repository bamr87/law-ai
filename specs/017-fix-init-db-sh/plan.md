# Plan: Fix init-db.sh — Correct Migration Paths + Delegate Postgres DDL to Django

> Companion to [spec.md](spec.md). Describes **how** we satisfy FR-1…FR-5.

## 1. Architecture Overview

This is a pure operator-script fix. No new services or APIs are introduced.

```mermaid
flowchart LR
  init-db.sh --> |cypher-shell loop| Neo4j[(Neo4j)]
  init-db.sh --> |manage.py migrate| Postgres[(Postgres)]
```

`init-db.sh` is an **operator script** (not auto-run by docker-compose). It is invoked manually (e.g. by `make reset-db` or during onboarding) from a context where both `cypher-shell` and `python manage.py` are reachable — i.e. with the stack running so the neo4j and postgres services are up. The `backend` service's own startup command already runs `python manage.py migrate --noinput` on every boot; `init-db.sh` is the explicit reset/onboarding path. After this fix the script will:
1. Discover `*.cypher` files under `backend/law_ai/core/neo4j/migrations/` (correct path).
2. Apply them in lexicographic order via `cypher-shell` (called from a container or host with neo4j reachable on `$NEO4J_URI`).
3. Call `python manage.py migrate --noinput` (replaces the dead `psql` loop; requires the backend container or a host venv with deps installed).

Note: `init-db.sh` is **not** mounted into the `postgres` container's `docker-entrypoint-initdb.d/` — Postgres initialisation (DB/user creation) is handled entirely by the `postgres:16-alpine` image's built-in env-var mechanism (`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`).

## 2. Component Changes

| Layer | File | Change |
|-------|------|--------|
| Infra script | `backend/scripts/init-db.sh` | Fix `NEO4J_MIGRATIONS` path; remove Postgres `psql` loop; add `manage.py migrate` call |
| Tests | `tests/test_configs.py` or `tests/test_init_db.py` | Assert old paths absent; assert `manage.py migrate` present; assert `bash -n` valid |

## 3. Data & Schema Migrations

No new migrations. The script will now correctly apply the seven existing Cypher migration files (`001`–`007`).

## 4. Tech Choices & Alternatives

- **Alternative A**: Delete `init-db.sh` and move Neo4j migration application into a Django management command. Rejected: adds complexity; `init-db.sh` is the documented operator entry-point in `Makefile` and `docker-compose.yml`.
- **Chosen approach**: Minimal in-place fix — correct the path variable and replace the dead SQL loop with `manage.py migrate`.

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| … | … | … | … |

If any choice deviates from [docs/constitution.md](../../docs/constitution.md) §2, write an ADR under `docs/adr/`.

## 5. Provenance & Audit Hook-up

How every new LLM call / tool call / DB write logs through `app.core.provenance`. Confirm node-creation paths set `source`, `confidence`, `ingest_timestamp`, `agent_version`.

## 6. HITL Gates

List every approval gate (spec, PR, deploy, ingestion). Map to the `human_approval_required` flag in agent outputs.

## 7. Test Strategy

- Unit tests: paths, mocks.
- Integration: which docker services required.
- LegalBench subset to run before/after.
- Frontend: Vitest + RTL files.

## 8. Rollout

- Local docker compose: works after `make dev`.
- Feature flag (if any) and default.
- Backfill / re-ingest needed? If yes, script path.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| … | low/med/high | low/med/high | … |

## 10. Estimated Effort

Story points / agent-hours; flag any task that needs human pairing.
