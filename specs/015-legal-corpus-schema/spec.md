# Spec: Legal Corpus Schema (Statutes, Codes, Ordinances, Regulations, Derived Documents)

- **ID**: 015-legal-corpus-schema
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-05-09
- **Roadmap Epic**: Legal corpus + Hybrid GraphRAG foundation (umbrella plan in session memory `/memories/session/plan.md`).
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §1 (open-source / privacy-first), §4 (provenance), §11 (continuous-evolution).

## 1. Problem & Motivation

Today the Neo4j data model is opinion-centric: only `Case` and `Citation` nodes exist (see [docs/data-model.md](../../docs/data-model.md)). The platform cannot store statutes, codes, ordinances, or regulations, nor can it persist agent-generated analyses as first-class retrievable content. Without a typed substrate for primary law and derived documents, we cannot ingest Colorado Revised Statutes (spec 016), build a real GraphRAG retriever (spec 018), or close the self-evolving feedback loop (spec 019). This spec lays the schema foundation for the remaining four specs in the corpus epic.

## 2. Goals

- **G1**: Define a typed Neo4j schema for `Statute`, `StatuteSection`, `Ordinance`, `OrdinanceSection`, `Regulation`, `Code`, `Jurisdiction`, `Court`, and `DerivedDocument` nodes plus the relationships needed to reason about them.
- **G2**: Add Pydantic domain models mirroring the new node types so ingestion and retrieval can pass typed payloads end-to-end.
- **G3**: Generalize the Postgres `pending_review` table with a `kind` discriminator so future statute / ordinance / derived-doc HITL items reuse the spec-004 quarantine flow.
- **G4**: Document the new schema in [docs/data-model.md](../../docs/data-model.md) with the same property-table style used for `Case` / `Citation`.

## 3. Non-Goals

- **NG1**: Wiring any actual ingestion source (Colorado, Denver, federal). That is spec 016.
- **NG2**: Generating embeddings or instantiating Chroma. That is spec 017.
- **NG3**: Building the GraphRAG retriever or modifying agent crews. That is spec 018.
- **NG4**: Writing back agent outputs as `DerivedDocument` rows. That is spec 019. (We add the *node label* + constraint here; we do not write to it yet.)
- **NG5**: Writing a back-fill / data-migration utility for existing `Case` nodes — they keep their current shape; new node labels are additive.

## 4. User Stories

- As an **ingestion engineer** building spec 016, I want a typed `StatuteSection` Pydantic model with mandatory provenance, so my Colorado parser can hand the commit layer a structured payload.
- As a **graph engineer** building spec 018, I want unique constraints + fulltext indexes on statute and opinion text, so hybrid retrieval can do an O(1) lookup by id and a fast lexical pre-filter.
- As an **operator** running HITL review, I want one `pending_review` queue with a `kind` column, so I can triage statutes, opinions, and derived documents in a single pane.

## 5. Functional Requirements

- **FR-1**: A new Cypher migration creates uniqueness constraints on `Statute.id`, `StatuteSection.id`, `Ordinance.id`, `OrdinanceSection.id`, `Regulation.id`, `Code.id`, `Jurisdiction.code`, `Court.id`, and `DerivedDocument.id`.
- **FR-2**: A new Cypher migration creates Neo4j fulltext indexes covering `(:StatuteSection)` on `text`/`heading` and `(:Case)` on `title`/`holding_summary`.
- **FR-3**: A new Cypher migration creates a range index on `effective_from` for `:Statute`, `:StatuteSection`, `:Ordinance`, `:OrdinanceSection`, `:Regulation`.
- **FR-4**: A new Cypher migration declares the `DerivedDocument` label with a uniqueness constraint on `id` and a property-existence constraint on `agent_version`.
- **FR-5**: New Pydantic models in `backend/lawgraph/core/schemas/legal_documents.py` for: `Jurisdiction`, `Court`, `Code`, `Statute`, `StatuteSection`, `Ordinance`, `OrdinanceSection`, `Regulation`, `DerivedDocument`. Every model carries the constitution §4 provenance fields (`source`, `source_url`, `confidence`, `ingest_timestamp`, `agent_version`).
- **FR-6**: `ingestionapp.PendingReview` gains a `kind` field (CharField, default `"case"`, db-indexed) plus a Django + database migration that adds the column with a back-fill `UPDATE pending_review SET kind = 'case' WHERE kind IS NULL` for any pre-existing rows. The migration follows the same `SeparateDatabaseAndState` + portable-DDL pattern as `0001_initial` so it works on Postgres and the SQLite test fixture.
- **FR-7**: [docs/data-model.md](../../docs/data-model.md) is extended with property tables for every new node type, an updated edge list, and a "Quarantine kinds" subsection that documents the new `kind` field.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every new Pydantic model must require `source`, `confidence`, `ingest_timestamp`, `agent_version` — the spec-001 `ExtractionResult` precedent. Validators enforce `0 ≤ confidence ≤ 1`.
- **NFR-MIGRATION-SAFETY-1**: All Cypher migrations use `IF NOT EXISTS`; the Postgres migration uses `ADD COLUMN IF NOT EXISTS` (Postgres path) and a portable `CREATE TABLE IF NOT EXISTS` shim (SQLite path) so reruns are idempotent and live data is preserved (see `/memories/repo/django-migrations.md`).
- **NFR-SEC-1**: No raw user input is ever interpolated into Cypher; all read/write helpers added later (spec 016+) will use parameter binding. This spec only adds DDL + types, no query helpers.
- **NFR-OSS-1**: No new third-party dependencies. Django, Pydantic v2, and the Neo4j driver are already in [backend/pyproject.toml](../../backend/pyproject.toml).

## 7. Data Model Impact

See [docs/data-model.md](../../docs/data-model.md) (updated by FR-7). Net additions:

**New node labels** (every node carries `id`, `source`, `source_url`, `confidence`, `ingest_timestamp`, `agent_version`):

| Label              | Required props beyond provenance                           |
| ------------------ | ---------------------------------------------------------- |
| `Jurisdiction`     | `code` (UNIQUE, e.g. `us-co`, `us-co-denver`), `name`, `level` (`federal`/`state`/`municipal`) |
| `Court`            | `id` (UNIQUE), `name`, `jurisdiction_code`                 |
| `Code`             | `id` (UNIQUE, e.g. `us-co/crs`), `title`                   |
| `Statute`          | `id` (UNIQUE, e.g. `us-co/crs/title-18`), `code_id`, `title`, `effective_from?`, `effective_to?` |
| `StatuteSection`   | `id` (UNIQUE, e.g. `us-co/crs/18-3-102`), `statute_id`, `citation`, `heading`, `text`, `effective_from?`, `effective_to?` |
| `Ordinance`        | `id` (UNIQUE), `jurisdiction_code`, `title`, `effective_from?`, `effective_to?` |
| `OrdinanceSection` | `id` (UNIQUE), `ordinance_id`, `citation`, `heading`, `text`, `effective_from?`, `effective_to?` |
| `Regulation`       | `id` (UNIQUE), `jurisdiction_code`, `citation`, `text`, `effective_from?`, `effective_to?` |
| `DerivedDocument`  | `id` (UNIQUE), `kind` (`analysis`/`summary`/`brief`/`holding`), `trace_id`, `body`, `is_hitl_approved` |

**New edges** (declared here by adding their endpoints to the schema; write paths land in later specs):

- `(:StatuteSection)-[:PART_OF]->(:Statute)`
- `(:Statute)-[:PART_OF]->(:Code)`
- `(:OrdinanceSection)-[:PART_OF]->(:Ordinance)`
- `(:Statute|:Ordinance|:Regulation|:Court)-[:IN_JURISDICTION]->(:Jurisdiction)`
- `(:StatuteSection)-[:AMENDS]->(:StatuteSection)` (temporal)
- `(:StatuteSection)-[:SUPERSEDES]->(:StatuteSection)` (temporal)
- `(:Case)-[:CITES_STATUTE {confidence}]->(:StatuteSection)`
- `(:Case)-[:INTERPRETS {confidence}]->(:StatuteSection)`
- `(:DerivedDocument)-[:DERIVED_FROM {confidence}]->(:Case|:StatuteSection|:OrdinanceSection|:Regulation|:DerivedDocument)`

**Postgres**: `pending_review` gains `kind text NOT NULL DEFAULT 'case'` with an index on `(kind, created_at DESC)`.

## 8. API Surface

None. This spec only introduces schema and types; no HTTP routes change.

## 9. Agent / Crew Impact

None directly. Downstream specs (016 for `IngestionScout`, 018 for `LegalAnalyst` / `PrecedentHunter`, 019 for any crew that emits derived docs) will import the new Pydantic models and write to the new node labels.

## 10. Acceptance Criteria

- **AC-1**: Running the full Neo4j migration set (`001`–`007`) on a fresh database is idempotent and produces all uniqueness, range, and fulltext indexes listed in FR-1 / FR-2 / FR-3 / FR-4. Verified by `SHOW INDEXES` parity assertion in a unit test that walks `backend/lawgraph/core/neo4j/migrations/*.cypher` and validates each statement is `IF NOT EXISTS`-guarded.
- **AC-2**: `from lawgraph.core.schemas.legal_documents import StatuteSection, DerivedDocument, …` succeeds and instantiating each new model with mandatory fields validates; instantiating with `confidence=1.5` raises `ValidationError`.
- **AC-3**: After `pytest backend/tests/ingestion/test_pending_review_kind.py`, a fresh test DB shows `PendingReview` rows can be created with `kind="statute"` and `kind="case"` (default), the `kind` column is db-indexed, and a row inserted via raw SQL without a `kind` value back-fills to `'case'`.
- **AC-4**: `python scripts/spec_validator.py` passes for `specs/015-legal-corpus-schema/` (every FR/NFR/AC referenced by at least one task).
- **AC-5**: [docs/data-model.md](../../docs/data-model.md) renders the new node tables and `tests/test_docs.py` (existing) still passes (no broken links).

## 11. LegalBench Impact

- Tasks affected: none directly. This spec is schema-only.
- Expected delta: **0 pp** (no reasoning paths changed).

## 12. Risks & Open Questions

- **R-1** (low): A future Neo4j migration runner will need to track applied migrations — today the runner is just a shell loop in `backend/scripts/init-db.sh` (which itself references the pre-rebrand `app/db/` path and is broken — see Follow-ups). Mitigation: keep migrations idempotent; backlog a proper runner in Phase B.
- **R-2** (low): Allowing five different node labels as the source-end of `:DERIVED_FROM` makes the relationship harder to type-check. Accept for v1; revisit if it complicates retrieval.
- **OQ-1**: ~~Should `PendingReview.kind` be an enum?~~ Resolved during /clarify: keep as a free-form `CharField(max_length=32)` with a constants module so spec 016/019 can add new kinds without a migration each time.

## 13. Out of Scope / Follow-ups

- Migration runner that tracks applied Cypher migrations in a `_migrations` Neo4j node (currently relies on `IF NOT EXISTS` only). Will be filed in Follow-ups.
- The stale `backend/scripts/init-db.sh` paths (`app/db/...`) — separate fix; filed in Follow-ups.
- ADR `0003-legal-corpus-schema.md` once the schema graduates to "shipped" — deferred until spec 016 also lands.
