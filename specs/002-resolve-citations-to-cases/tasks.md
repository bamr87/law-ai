# Tasks: 002 — Resolve Citations to Case Nodes

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — Extend `ExtractionResult` with `aliases`

- **Refs**: FR-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/models/extraction.py` (edit)
- **Steps**:
  1. Add `aliases: list[str] = Field(default_factory=list, description="Canonical normalized citation forms this case is known by")`.
- **Verify**: `pytest backend/tests/models -q` and `mypy app/models --strict` clean.

## T-002 — Thread `aliases` through `MERGE_CASE_CYPHER`

- **Refs**: FR-1, NFR-IDEMPOTENT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/db/queries.py` (edit)
  - `backend/app/db/neo4j_migrations/002_case_aliases.cypher` (new)
- **Steps**:
  1. Add `c.aliases = coalesce($aliases, [])` to both `ON CREATE SET` and `ON MATCH SET` clauses (idempotent; only overrides when caller passes a non-null list).
  2. Update `commit_extraction` to pass `aliases=result.aliases`.
  3. Author the migration that defaults existing nodes to `[]`.
- **Verify**: existing tests pass (`pytest backend/tests/ingestion -q`); migration is valid Cypher (loaded by migration runner).

## T-003 — Implement `citation_resolver` module

- **Refs**: FR-2, FR-3, NFR-PERF-1, NFR-AUDIT-1, AC-1, AC-3, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/db/citation_resolver.py` (new)
- **Steps**:
  1. `resolve_citations(session, normalized)` issues the single `UNWIND` query.
  2. `densify_extraction(session, result)` calls `resolve_citations` then mutates `result.citations[*].target_case_id` and emits provenance via `app.core.provenance`.
- **Verify**: `mypy app/db/citation_resolver.py --strict` clean.

## T-004 — Unit tests with `FakeAsyncSession`

- **Refs**: AC-1, AC-2, AC-3, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/db/__init__.py` (new)
  - `backend/tests/db/test_citation_resolver.py` (new)
- **Steps**:
  1. Build a minimal `FakeAsyncSession` recording `(cypher, params)` calls and yielding canned records.
  2. Cover AC-1 (resolves to existing case), AC-2 (idempotency via call count), AC-3 (no-match path issues exactly one query and zero edges).
- **Verify**: `pytest backend/tests/db -q --cov=app.db.citation_resolver` ≥ 85% line coverage.

## T-005 — Wire into `IngestionScout.run_and_commit`

- **Refs**: FR-4, NFR-HITL-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/ingestion/scout.py` (edit)
  - `backend/tests/ingestion/test_ingestion.py` (edit — extend existing test to assert `target_case_id` is populated)
- **Steps**:
  1. Insert `await densify_extraction(session, result)` between `extract` and `commit_extraction`.
- **Verify**: `pytest backend/tests/ingestion -q` green; full `pytest -q` ≥ 75% coverage.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- `## Follow-ups Discovered` section below populated.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- **BL-20260429-10** — *test-gap, med* — Add Docker-backed integration test for `densify_extraction` against a real Neo4j (currently only `FakeAsyncSession`).
- **BL-20260429-11** — *feature, med* — Backfill script `scripts/densify_existing.py` that re-runs `densify_extraction` over historical `:Case` nodes once aliases are populated.
- **BL-20260429-12** — *refactor, low* — Make `head(collect(c.id))` deterministic by adding a secondary `ORDER BY c.id` clause; matters when two cases share an alias (data-quality bug, but worth fencing off).
