# Data Model

Law AI's Neo4j knowledge graph + Postgres quarantine. Spec of record for the original opinion-only model: [001-ingest-courtlistener-opinions](../specs/001-ingest-courtlistener-opinions/spec.md). Schema-expansion spec: [015-legal-corpus-schema](../specs/015-legal-corpus-schema/spec.md).

> **Provenance is mandatory.** Every node persisted to Neo4j carries `source`, `source_url`, `confidence`, `ingest_timestamp`, and `agent_version` per [docs/constitution.md](constitution.md) §4. The Pydantic mixin enforcing this lives in [`law_ai.core.schemas.legal_documents.LegalProvenance`](../backend/law_ai/core/schemas/legal_documents.py).

## Nodes

### `Case`
| Property            | Type     | Notes                                  |
| ------------------- | -------- | -------------------------------------- |
| `id` (UNIQUE)       | string   | Source-prefixed, e.g. `12345`          |
| `title`             | string   | Case caption                           |
| `court`             | string   | e.g. "Supreme Court"                   |
| `decided_date`      | date     | ISO YYYY-MM-DD, optional               |
| `holding_summary`   | string   | Optional; indexed by fulltext (mig 007)|
| `aliases`           | string[] | Normalized citation forms (spec 002)   |
| `source`            | string   | e.g. `courtlistener`                   |
| `source_url`        | string   | Canonical URL                          |
| `confidence`        | float    | 0..1; ≥0.7 commits, < goes to review   |
| `ingest_timestamp`  | datetime | UTC                                    |
| `agent_version`     | string   | e.g. `0.1.0`                           |

### `Citation`
| Property                | Type   | Notes                                |
| ----------------------- | ------ | ------------------------------------ |
| `normalized` (UNIQUE)   | string | Lowercased eyecite reporter form     |
| `text`                  | string | Verbatim citation text               |

### `Jurisdiction` _(spec 015)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `code` (UNIQUE)     | string   | e.g. `us-co`, `us-co-denver`, `us-fed`         |
| `name`              | string   | Human-readable, e.g. `Colorado`                |
| `level`             | string   | `federal` / `state` / `municipal` / `tribal` / `international` |

### `Court` _(spec 015)_
| Property                | Type   | Notes                                |
| ----------------------- | ------ | ------------------------------------ |
| `id` (UNIQUE)           | string | e.g. `co-supreme`                    |
| `name`                  | string |                                      |
| `jurisdiction_code`     | string | FK → `Jurisdiction.code`             |

### `Code` _(spec 015)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `id` (UNIQUE)       | string   | e.g. `us-co/crs`                               |
| `title`             | string   | e.g. `Colorado Revised Statutes`               |
| `jurisdiction_code` | string   | FK → `Jurisdiction.code`                       |

### `Statute` _(spec 015)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `id` (UNIQUE)       | string   | e.g. `us-co/crs/title-18`                      |
| `code_id`           | string   | FK → `Code.id`                                 |
| `title`             | string   |                                                |
| `citation`          | string   | Optional Bluebook-style citation               |
| `effective_from`    | date     | Optional; range-indexed (mig 005)              |
| `effective_to`      | date     | Optional                                       |

### `StatuteSection` _(spec 015 — primary unit of retrieval for statutory law)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `id` (UNIQUE)       | string   | e.g. `us-co/crs/18-3-102`                      |
| `statute_id`        | string   | FK → `Statute.id`                              |
| `citation`          | string   | e.g. `C.R.S. § 18-3-102`                       |
| `heading`           | string   | Section heading                                |
| `text`              | string   | Body text; indexed by fulltext (mig 007)       |
| `effective_from`    | date     | Optional; range-indexed (mig 005)              |
| `effective_to`      | date     | Optional                                       |

### `Ordinance` / `OrdinanceSection` _(spec 015)_

Same shape as `Statute` / `StatuteSection` but keyed on `jurisdiction_code` (e.g. `us-co-denver`) rather than `code_id`. `OrdinanceSection.text` is fulltext-indexed (mig 007).

### `Regulation` _(spec 015)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `id` (UNIQUE)       | string   | e.g. `us-co/ccr/8-1-203`                       |
| `jurisdiction_code` | string   | FK → `Jurisdiction.code`                       |
| `citation`          | string   | e.g. `8 CCR 1206-1`                            |
| `text`              | string   | Body text; indexed by fulltext (mig 007)       |
| `effective_from`    | date     | Optional; range-indexed (mig 005)              |

### `DerivedDocument` _(spec 015 — first-class home for AI-generated outputs)_
| Property              | Type     | Notes                                                                                |
| --------------------- | -------- | ------------------------------------------------------------------------------------ |
| `id` (UNIQUE)         | string   | e.g. `analysis/<trace_id>`                                                           |
| `kind`                | string   | `analysis` / `summary` / `brief` / `holding` (existence-required by mig 006)         |
| `trace_id`            | string   | FK → `audit.AuditEvent.trace_id` of the producing run                                |
| `body`                | string   | Generated text; fulltext-indexed (mig 007)                                           |
| `is_hitl_approved`    | bool     | Set by HITL flow before retrieval considers the doc authoritative                    |
| `source_node_ids`     | string[] | ids of `Case` / `StatuteSection` / etc. this was derived from (also via `:DERIVED_FROM`) |
| `agent_version`       | string   | Existence-required by mig 006                                                        |

> Spec 019 will write to this label. Spec 015 only declares the schema.

## Edges

### Opinion-centric (spec 001 / 002)

- `(:Case)-[:HAS_CITATION]->(:Citation)` — opinion contains citation text.
- `(:Case)-[:CITES {confidence,context}]->(:Case)` — created when a `Citation` resolves to another known `Case`.

### Statutory / regulatory _(spec 015)_

- `(:StatuteSection)-[:PART_OF]->(:Statute)`
- `(:Statute)-[:PART_OF]->(:Code)`
- `(:OrdinanceSection)-[:PART_OF]->(:Ordinance)`
- `(:Statute|:Ordinance|:Regulation|:Court)-[:IN_JURISDICTION]->(:Jurisdiction)`

### Temporal _(spec 015)_

- `(:StatuteSection)-[:AMENDS]->(:StatuteSection)`
- `(:StatuteSection)-[:SUPERSEDES]->(:StatuteSection)`

### Cross-corpus reasoning _(spec 015 — write paths land in spec 016+)_

- `(:Case)-[:CITES_STATUTE {confidence}]->(:StatuteSection)`
- `(:Case)-[:INTERPRETS {confidence}]->(:StatuteSection)`

### Derived corpus _(spec 015 — write paths land in spec 019)_

- `(:DerivedDocument)-[:DERIVED_FROM {confidence}]->(:Case|:StatuteSection|:OrdinanceSection|:Regulation|:DerivedDocument)`

## Constraints + Indexes

Defined under [backend/law_ai/core/neo4j/migrations/](../backend/law_ai/core/neo4j/migrations/). All migrations are `IF NOT EXISTS`-guarded and forward-only (spec 015 NFR-MIGRATION-SAFETY-1).

| File                                      | What it adds                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| `001_case_constraints.cypher`             | Unique `Case.id`, `Citation.normalized`                                   |
| `002_case_aliases.cypher`                 | `Case.aliases = []` back-fill (spec 002)                                  |
| `003_statute_constraints.cypher`          | Unique `Jurisdiction.code`, `Court.id`, `Code.id`, `Statute.id`, `StatuteSection.id` |
| `004_ordinance_regulation.cypher`         | Unique `Ordinance.id`, `OrdinanceSection.id`, `Regulation.id`             |
| `005_temporal_indexes.cypher`             | Range index on `effective_from` for all statutory / regulatory labels     |
| `006_derived_document.cypher`             | Unique `DerivedDocument.id`; existence on `agent_version` + `kind`        |
| `007_fulltext_indexes.cypher`             | Fulltext on `Case`, `StatuteSection`, `OrdinanceSection`, `Regulation`, `DerivedDocument` |

## Idempotency

All writes use `MERGE` keyed on the unique property, so re-running ingestion against the same source IDs creates **0 duplicate** nodes/edges (spec 001 AC-2). All Cypher migrations are themselves idempotent (validated in [`backend/tests/core/test_neo4j_migrations.py`](../backend/tests/core/test_neo4j_migrations.py)).

## Quarantine

Items below `confidence = 0.7` never enter the graph; they land in `pending_review` (Postgres table or JSONL fallback at `backend/var/pending_review/<date>.jsonl`).

### Quarantine kinds _(spec 015)_

`pending_review.kind` (CharField, default `'case'`, db-indexed) discriminates what lives in the queue so a single Django admin pane can triage every kind of HITL item. Constants live in [`law_ai.ingestionapp.quarantine_kinds`](../backend/law_ai/ingestionapp/quarantine_kinds.py):

| Constant                 | Value               | Producer (planned)                                    |
| ------------------------ | ------------------- | ----------------------------------------------------- |
| `KIND_CASE`              | `case`              | `IngestionScout` (spec 001) — default                 |
| `KIND_STATUTE`           | `statute`           | spec 016 statute parser                               |
| `KIND_STATUTE_SECTION`   | `statute_section`   | spec 016 statute parser                               |
| `KIND_ORDINANCE`         | `ordinance`         | spec 016 Denver ordinance parser                      |
| `KIND_ORDINANCE_SECTION` | `ordinance_section` | spec 016 Denver ordinance parser                      |
| `KIND_REGULATION`        | `regulation`        | future federal/state regulation ingestion             |
| `KIND_DERIVED`           | `derived`           | spec 019 — low-confidence agent outputs awaiting HITL |

Adding a new kind is a code-only change (no migration) thanks to `CharField(max_length=32)`.
