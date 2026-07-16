# Tasks: Legal Corpus Schema

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces coverage.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Add Cypher migrations 003–007

- **Refs**: FR-1, FR-2, FR-3, FR-4, NFR-MIGRATION-SAFETY-1, NFR-SEC-1, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/neo4j/migrations/003_statute_constraints.cypher` (new)
  - `backend/law_ai/core/neo4j/migrations/004_ordinance_regulation.cypher` (new)
  - `backend/law_ai/core/neo4j/migrations/005_temporal_indexes.cypher` (new)
  - `backend/law_ai/core/neo4j/migrations/006_derived_document.cypher` (new)
  - `backend/law_ai/core/neo4j/migrations/007_fulltext_indexes.cypher` (new)
- **Steps**:
  1. Author the five `.cypher` files with `CREATE CONSTRAINT … IF NOT EXISTS` / `CREATE INDEX … IF NOT EXISTS` / `CREATE FULLTEXT INDEX … IF NOT EXISTS` statements covering every label in spec §7.
  2. Each file ends with a comment block explaining what it adds and why it is forward-only.
- **Verify**:
  - `backend/tests/core/test_neo4j_migrations.py` (T-004) passes.

## T-002 — Pydantic models for legal documents

- **Refs**: FR-5, NFR-AUDIT-1, NFR-OSS-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/schemas/legal_documents.py` (new)
  - `backend/law_ai/core/schemas/__init__.py` (re-export)
- **Steps**:
  1. Define a `LegalProvenance` mixin Pydantic model carrying `source` / `source_url` / `confidence` / `ingest_timestamp` / `agent_version`.
  2. Define `Jurisdiction`, `Court`, `Code`, `Statute`, `StatuteSection`, `Ordinance`, `OrdinanceSection`, `Regulation`, `DerivedDocument` models inheriting the mixin.
  3. Re-export from `core/schemas/__init__.py`.
- **Verify**:
  - `backend/tests/models/test_legal_document_schemas.py` (T-005) passes.
  - `cd backend && mypy law_ai/core/schemas --strict` clean.

## T-003 — Generalize `PendingReview` with `kind`

- **Refs**: FR-6, NFR-MIGRATION-SAFETY-1, AC-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/ingestionapp/models.py` (extend)
  - `backend/law_ai/ingestionapp/migrations/0002_pending_review_kind.py` (new)
  - `backend/law_ai/ingestionapp/quarantine_kinds.py` (new — constants)
- **Steps**:
  1. Add `kind = models.CharField(max_length=32, default="case", db_index=True)` to `PendingReview`.
  2. Author migration `0002_pending_review_kind.py` using `SeparateDatabaseAndState` with vendor-aware `RunPython` (Postgres `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`, SQLite portable `ALTER TABLE`).
  3. Add `quarantine_kinds.py` exporting `KIND_CASE`, `KIND_STATUTE`, `KIND_ORDINANCE`, `KIND_REGULATION`, `KIND_DERIVED`.
- **Verify**:
  - `backend/tests/ingestion/test_pending_review_kind.py` (T-006) passes.
  - `cd backend && python manage.py makemigrations --check --dry-run` is a no-op.

## T-004 — Test: Neo4j migration files are idempotent + complete

- **Refs**: FR-1, FR-2, FR-3, FR-4, NFR-MIGRATION-SAFETY-1, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/core/test_neo4j_migrations.py` (new)
- **Steps**:
  1. Discover all `.cypher` files under `backend/law_ai/core/neo4j/migrations/`.
  2. Assert every `CREATE CONSTRAINT|INDEX|FULLTEXT INDEX` statement contains `IF NOT EXISTS`.
  3. Assert the union of declared constraint names covers the labels listed in spec FR-1.
- **Verify**: `cd backend && pytest tests/core/test_neo4j_migrations.py -q`.

## T-005 — Test: Pydantic schemas validate provenance + bounds

- **Refs**: FR-5, NFR-AUDIT-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/models/test_legal_document_schemas.py` (new)
  - `backend/tests/models/__init__.py` (new, empty if needed)
- **Steps**:
  1. Round-trip-instantiate each model with valid input.
  2. Assert `ValidationError` when `confidence` is out of range or required provenance fields are missing.
- **Verify**: `cd backend && pytest tests/models/test_legal_document_schemas.py -q`.

## T-006 — Test: `PendingReview.kind` column behavior

- **Refs**: FR-6, AC-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/ingestion/test_pending_review_kind.py` (new)
- **Steps**:
  1. Create `PendingReview` rows with explicit `kind="statute"` and default (omitted) — assert default = `"case"`.
  2. Insert via raw SQL without `kind` (where the DB allows) and assert it back-fills to `'case'`.
  3. Introspect connection constraints / indexes for `pending_review_kind`.
- **Verify**: `cd backend && pytest tests/ingestion/test_pending_review_kind.py -q`.

## T-007 — Update [docs/data-model.md](../../docs/data-model.md)

- **Refs**: FR-7, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/data-model.md` (extend)
- **Steps**:
  1. Add property tables for every new node label.
  2. Update the Edges section with the new relationships listed in spec §7.
  3. Add a "Quarantine kinds" subsection describing the new `kind` discriminator.
- **Verify**: `cd backend && pytest tests/test_docs.py -q` (workspace `tests/`) — link checker still green.

## T-008 — Update [BACKLOG.md](../../BACKLOG.md) with follow-ups

- **Refs**: AC-4 (constitution §11), spec §13
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `BACKLOG.md`
- **Steps**:
  1. Add follow-ups for the broken `init-db.sh` paths and the missing migration runner.
  2. Mirror them in `## Follow-ups Discovered` below.
- **Verify**: `python scripts/backlog_lint.py && python scripts/spec_validator.py`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- `cd backend && pytest tests/core tests/models tests/ingestion -q` green.
- `make lint` green.
- LegalBench delta: **0 pp** (no reasoning changed) — recorded in PR.
- `## Follow-ups Discovered` populated below; mirrored in `BACKLOG.md`.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260509-01 — *infra, high* — `backend/scripts/init-db.sh` references the pre-rebrand `app/db/neo4j_migrations` and `app/db/postgres_migrations` paths; never picks up `backend/law_ai/core/neo4j/migrations/*.cypher`. Fix path + add Postgres-side runner that complements Django migrations (only for Neo4j Cypher files now that all Postgres DDL lives in Django migrations).
- BL-20260509-02 — *infra, med* — Add a real Cypher migration runner that records applied migrations in a `(:_Migration {id})` Neo4j node so non-idempotent migrations become possible later (e.g. data back-fills).
- BL-20260509-03 — *test-gap, med* — Docker-backed integration test that actually applies `001`–`007` against a live Neo4j and runs `SHOW CONSTRAINTS` / `SHOW INDEXES` to confirm shape; the unit test added in T-004 only validates the file contents.
