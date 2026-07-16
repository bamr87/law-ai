# Spec: Fix init-db.sh — Correct Migration Paths + Delegate Postgres DDL to Django

- **ID**: 017-fix-init-db-sh
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-05-10
- **Backlog Origin**: BL-20260509-01
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

`backend/scripts/init-db.sh` was written before the Django rebrand and still references two
paths that no longer exist:

| Variable | Current (broken) value | Correct path |
|---|---|---|
| `NEO4J_MIGRATIONS` | `$REPO_ROOT/app/db/neo4j_migrations` | `$REPO_ROOT/law_ai/core/neo4j/migrations` |
| `PG_MIGRATIONS` | `$REPO_ROOT/app/db/postgres_migrations` | _(delegated to Django — no raw SQL loop needed)_ |

Because the glob `"$NEO4J_MIGRATIONS"/*.cypher` matches nothing, no Cypher migrations
(`001_case_constraints.cypher` … `007_fulltext_indexes.cypher`) are applied on a fresh stack.
Because Postgres DDL now lives entirely in Django ORM migrations, the `psql … -f *.sql` loop
is dead code — the correct way to prime Postgres is `python manage.py migrate`.

This breakage is invisible during development when the Docker volume already exists, but it
causes silent data-model gaps on fresh installs (CI, onboarding, `make reset-db`).

## 2. Origin & Background

- **BL-20260509-01** (infra, high) — surfaced by specs/015-legal-corpus-schema T-008.

## 3. Goals

- G1: Correct the `NEO4J_MIGRATIONS` path so all seven Cypher migrations are applied by
  `init-db.sh` on a fresh stack.
- G2: Remove the dead `psql`-based Postgres loop and replace it with a call to
  `python manage.py migrate --noinput` so Postgres schema is always driven by Django
  migrations (single source of truth).
- G3: Keep the script self-contained — no new external dependencies.

## 4. Non-Goals

- NG1: A true Cypher migration tracker (recording applied migrations in `(:_Migration)` nodes)
  — that is BL-20260509-02 and out of scope here.
- NG2: Changing the Cypher migration files themselves.
- NG3: Altering Docker Compose or Makefile targets.

## 5. User Stories

- As a developer onboarding on a fresh machine, I want `make reset-db` to fully initialize
  both Neo4j and Postgres so I can start the stack without manual intervention.
- As a CI job, I want `init-db.sh` to be idempotent and apply all schema DDL so integration
  tests against a live DB always pass.

## 6. Functional Requirements

- **FR-1**: `init-db.sh` resolves `NEO4J_MIGRATIONS` to
  `<repo_root>/law_ai/core/neo4j/migrations` (relative to the `backend/` directory, which
  is one level above `backend/scripts/`).
- **FR-2**: `init-db.sh` applies every `*.cypher` file found in that directory via
  `cypher-shell`, in lexicographic order.
- **FR-3**: `init-db.sh` removes the Postgres `psql` loop and instead runs
  `python manage.py migrate --noinput` (with `DJANGO_SETTINGS_MODULE` defaulting to
  `law_ai.settings.dev`).
- **FR-4**: The script remains idempotent — running it twice against a running stack must
  not error (Cypher migrations already use `IF NOT EXISTS`; Django migrate is idempotent).
- **FR-5**: If no `.cypher` files are found (e.g. the directory is empty), the script logs a
  warning and continues rather than silently exiting the loop without notice.

## 7. Non-Functional Requirements

- **NFR-SEC-1**: No credentials are hard-coded beyond the already-present dev defaults;
  all sensitive values remain env-var driven.
- **NFR-AUDIT-1**: Not applicable — this is an operator script, not an agent path.
- **NFR-HITL-1**: Not applicable — no LLM or ingestion path is touched.
- **NFR-MIGRATION-SAFETY-1**: The fix must not drop or truncate any data; it only corrects
  a path and replaces a dead code block.

## 8. API Surface

None. This change is confined to `backend/scripts/init-db.sh`.

## 9. Agent / Crew Impact

None.

## 10. Acceptance Criteria

- **AC-1**: After applying the fix, running
  `bash backend/scripts/init-db.sh` (with `NEO4J_USER`, `NEO4J_PASSWORD`, and
  `POSTGRES_URL_PSQL` set, or using dev defaults) applies all seven Cypher migration files
  without error — verified by `cypher-shell --version` availability check or a mock.
- **AC-2**: The Postgres `psql` loop is absent from the script; `python manage.py migrate
  --noinput` appears in its place.
- **AC-3**: `grep -q "app/db/neo4j_migrations\|app/db/postgres_migrations" backend/scripts/init-db.sh`
  exits non-zero (old paths are gone).
- **AC-4**: `bash -n backend/scripts/init-db.sh` exits 0 (script is syntactically valid).
- **AC-5**: A unit test (`tests/test_configs.py` or a new `tests/test_init_db.py`) asserts
  AC-3 and AC-4 via `subprocess`.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp (no reasoning logic changed).

## 12. Risks & Open Questions

- **R-1**: `python manage.py migrate` requires a running Postgres instance. The script
  already sleeps 5 s at startup, which is sufficient for Docker Compose healthcheck-ordered
  starts. No change needed.
- **R-2**: `cypher-shell` must be on `PATH` inside the container where the script runs.
  This was already a hard requirement; no change needed.

## 13. Out of Scope / Follow-ups

- BL-20260509-02 — Cypher migration tracker (`(:_Migration)` node).
- BL-20260509-03 — Docker-backed integration test against live Neo4j.
