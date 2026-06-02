# Tasks: Fix init-db.sh — Correct Migration Paths + Delegate Postgres DDL to Django

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Fix NEO4J_MIGRATIONS path and replace Postgres psql loop

- **Refs**: FR-1, FR-2, FR-3, FR-4, FR-5, NFR-SEC-1, NFR-AUDIT-1, NFR-HITL-1, NFR-MIGRATION-SAFETY-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/scripts/init-db.sh` (modify)
- **Steps**:
  1. Change `NEO4J_MIGRATIONS="$REPO_ROOT/app/db/neo4j_migrations"` to
     `NEO4J_MIGRATIONS="$REPO_ROOT/lawgraph/core/neo4j/migrations"`.
  2. Remove the `PG_MIGRATIONS` variable and the `for f in "$PG_MIGRATIONS"/*.sql` loop
     entirely.
  3. Add `DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-lawgraph.settings.dev}"` export
     before the `manage.py` call.
  4. Replace the removed Postgres block with:
     ```bash
     echo "==> Applying Postgres migrations (Django)"
     cd "$REPO_ROOT" && python manage.py migrate --noinput
     ```
  5. Add a warning if the Cypher glob matches no files:
     ```bash
     shopt -s nullglob
     cypher_files=("$NEO4J_MIGRATIONS"/*.cypher)
     if [[ ${#cypher_files[@]} -eq 0 ]]; then
       echo "WARNING: No .cypher files found under $NEO4J_MIGRATIONS — skipping Neo4j migrations."
     fi
     for f in "${cypher_files[@]}"; do …; done
     ```
- **Verify**:
  - `bash -n backend/scripts/init-db.sh` exits 0.
  - `grep -q "app/db/neo4j_migrations\|app/db/postgres_migrations" backend/scripts/init-db.sh` exits non-zero (old paths absent).
  - `grep -q "manage.py migrate" backend/scripts/init-db.sh` exits 0.

## T-002 — Add or extend a test asserting the script correctness

- **Refs**: FR-1, FR-3, AC-3, AC-4, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `tests/test_configs.py` (extend) _or_ `tests/test_init_db.py` (new if a new file is
    cleaner)
- **Steps**:
  1. Use `subprocess.run(["bash", "-n", "backend/scripts/init-db.sh"])` and assert exit 0
     (AC-4).
  2. Read `backend/scripts/init-db.sh` as text and assert neither `app/db/neo4j_migrations`
     nor `app/db/postgres_migrations` appears (AC-3).
  3. Assert `manage.py migrate` appears in the script text (AC-2).
- **Verify**:
  - `cd /Users/bamr87/law-ai && pytest tests/test_configs.py -q` (or `test_init_db.py`) green.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint` green; `pytest tests/test_configs.py` (or equivalent) green.
- LegalBench delta: 0 pp (no reasoning logic changed).
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260511-01 — *infra, med* — Add a real Cypher migration runner that records applied migrations in a `(:_Migration {id})` Neo4j node so non-idempotent migrations (e.g. data back-fills) become safe later. Resolves overlap with BL-20260509-02. _Surfaced in:_ specs/017-fix-init-db-sh implementation.
- BL-20260511-02 — *test-gap, low* — Add a Docker-backed integration smoke test that runs `init-db.sh` against live Neo4j and Postgres containers and confirms all seven Cypher migrations were applied (`SHOW CONSTRAINTS`). Resolves overlap with BL-20260509-03. _Surfaced in:_ specs/017-fix-init-db-sh implementation.
