# Data Model

Law AI's Neo4j knowledge graph + Postgres quarantine. Spec of record for the original opinion-only model: [001-ingest-courtlistener-opinions](../specs/001-ingest-courtlistener-opinions/spec.md). Schema-expansion spec: [015-legal-corpus-schema](../specs/015-legal-corpus-schema/spec.md).

> **Provenance is mandatory.** Every node persisted to Neo4j carries `source`, `source_url`, `confidence`, `ingest_timestamp`, and `agent_version` per [docs/constitution.md](constitution.md) §4. The Pydantic mixin enforcing this lives in [`law_ai.core.schemas.legal_documents.LegalProvenance`](../backend/law_ai/core/schemas/legal_documents.py).

## Nodes

### `Case`
| Property            | Type     | Notes                                  |
| ------------------- | -------- | -------------------------------------- |
| `id` (UNIQUE)       | string   | Source's own ID (e.g. raw CourtListener opinion id, unprefixed) |
| `title`             | string   | Case caption                           |
| `court`             | string   | e.g. "Supreme Court"                   |
| `decided_at`        | datetime | Populated date-only in practice; optional |
| `holding_summary`   | string   | Optional; indexed by fulltext (mig 007)|
| `aliases`           | string[] | Normalized citation forms (spec 002)   |
| `archived_at`       | datetime | Soft-delete marker per [constitution §4](constitution.md); **read-only today** — `graph_rag.py` filters it out of retrieval, no write path sets it yet |
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
| `effective_from`    | date     | Declared, range-indexed (mig 005); **not populated** by the spec-016 ingestion path — `MERGE_STATUTE_CYPHER` never sets it |
| `effective_to`      | date     | Declared; **not populated** — same gap         |

### `StatuteSection` _(spec 015 — primary unit of retrieval for statutory law)_
| Property            | Type     | Notes                                          |
| ------------------- | -------- | ---------------------------------------------- |
| `id` (UNIQUE)       | string   | e.g. `us-co/crs/18-3-102`                      |
| `statute_id`        | string   | FK → `Statute.id`                              |
| `citation`          | string   | e.g. `C.R.S. § 18-3-102`                       |
| `heading`           | string   | Section heading                                |
| `text`              | string   | Body text; indexed by fulltext (mig 007)       |
| `effective_from`    | date     | Optional; range-indexed (mig 005); populated by `StatuteScout` when the source gives a date |
| `effective_to`      | date     | Declared; **not populated** — `StatuteSectionPayload` has no `effective_to` field |
| `archived_at`       | datetime | Soft-delete marker per [constitution §4](constitution.md); **read-only today** — `graph_rag.py` filters it out of retrieval, no write path sets it yet |

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

> No shipped spec writes to this label yet — schema and constraints only (spec 015). Spec 019 (`019-lsat-content-autogen`) does **not** use it: LSAT question generation writes to a JSONL store (`backend/var/lsat_proposals/proposals.jsonl`), not Neo4j. See the implementation-status note below.

## Edges

### Opinion-centric (spec 001 / 002)

- `(:Case)-[:HAS_CITATION {confidence,ingest_timestamp}]->(:Citation)` — opinion contains citation text.
- `(:Case)-[:CITES {confidence,ingest_timestamp}]->(:Case)` — created when a `Citation` resolves to another known `Case`.

### Statutory / regulatory _(spec 015)_

- `(:StatuteSection)-[:PART_OF]->(:Statute)`
- `(:Statute)-[:PART_OF]->(:Code)`
- `(:OrdinanceSection)-[:PART_OF]->(:Ordinance)`
- `(:Code|:Statute|:Ordinance|:Regulation|:Court)-[:IN_JURISDICTION]->(:Jurisdiction)` — declared for all five; only `Code` and `Statute` have an actual `MERGE` write path today ([`statute_queries.py`](../backend/law_ai/core/neo4j/statute_queries.py)). `Ordinance`, `Regulation`, `Court` have constraints/indexes only — no `MERGE` for any of them exists anywhere in the codebase yet.

### Temporal _(spec 015)_

- `(:StatuteSection)-[:AMENDS]->(:StatuteSection)`
- `(:StatuteSection)-[:SUPERSEDES]->(:StatuteSection)`

### Cross-corpus reasoning _(spec 015 — declared only, no write path yet)_

- `(:Case)-[:CITES_STATUTE {confidence}]->(:StatuteSection)`
- `(:Case)-[:INTERPRETS {confidence}]->(:StatuteSection)`

Spec 016 explicitly put these edges out of scope, deferring them to a future spec ([spec 016 §scope](../specs/016-ingest-colorado-statutes/spec.md)). The real GraphRAG retriever that shipped (`028-real-graphrag-retrieval`, [`graph_rag.py`](../backend/law_ai/agents_runtime/tools/graph_rag.py)) only reads `Case`/`StatuteSection` fulltext plus `CITES` expansion — it does not create these edges. Tracked as `BL-20260509-07` in [BACKLOG.md](../BACKLOG.md); no spec currently owns it.

### Derived corpus _(spec 015 — declared only, no write path yet)_

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

Items below `confidence = 0.7` never enter the graph; they land in `pending_review` (Postgres table, `law_ai.ingestionapp.models.PendingReview`, with a JSONL fallback at `backend/var/pending_review/<date>.jsonl` when the Celery dispatch itself fails).

### `PendingReview` fields

| Field           | Type              | Notes                                                              |
| --------------- | ----------------- | ------------------------------------------------------------------- |
| `id`            | text (PK)         | Source-supplied id of the quarantined item                          |
| `source`        | text, indexed     | Producer identifier                                                 |
| `kind`          | `CharField(32)`, indexed, default `case` | See kinds table below                                |
| `payload`       | JSON               | Raw extraction payload                                              |
| `confidence`    | float              | Producer confidence that triggered quarantine                       |
| `reason`        | text               | Optional free-text reason                                           |
| `created_at`    | datetime, indexed | Auto-set on insert                                                   |
| `reviewed_at`   | datetime, optional | Set when a human decides                                            |
| `approved`      | bool, optional      | `None` = undecided, `True`/`False` = human decision                |
| `reviewer`      | text               | Reviewer identity, free-text (spec 029)                             |
| `review_note`   | text               | Reviewer rationale, free-text (spec 029)                            |
| `committed_at`  | datetime, optional, indexed | Set once the approved item reaches Neo4j (spec 029)        |
| `commit_error`  | text               | Non-empty when a commit attempt failed (spec 029)                   |

Spec 029 (`029-close-ingestion-hitl-loop`) closed the approve → commit loop: before it, flipping `approved = True` in Django admin had no consumer. Now `commit_approved_reviews_task` (Celery, [`ingestionapp/tasks.py`](../backend/law_ai/ingestionapp/tasks.py)) sweeps rows where `approved = True AND committed_at IS NULL` and calls `IngestionScout.run_and_commit(..., force_commit=True)` per constitution §12 I1 (all graph writes go through the scout, never direct from the sweep). The sweep is idempotent — already-committed rows are skipped — and records `committed_at` or `commit_error` on every attempt so a failed graph write stays visible instead of silently reading as "approved."

### Quarantine kinds _(spec 015)_

`pending_review.kind` (CharField, default `'case'`, db-indexed) discriminates what lives in the queue so a single Django admin pane can triage every kind of HITL item. Constants live in [`law_ai.ingestionapp.quarantine_kinds`](../backend/law_ai/ingestionapp/quarantine_kinds.py):

| Constant                 | Value               | Producer                                                          |
| ------------------------ | -------------------- | ------------------------------------------------------------------ |
| `KIND_CASE`              | `case`               | `IngestionScout` (spec 001) — shipped, default                    |
| `KIND_STATUTE`           | `statute`            | Declared for the discriminator; not actually produced anywhere — `StatuteScout` commits `Jurisdiction`/`Code`/`Statute` directly alongside any high-confidence section rather than quarantining at the statute level |
| `KIND_STATUTE_SECTION`   | `statute_section`    | `StatuteScout` (spec 016) — shipped, [`statute_scout.py`](../backend/law_ai/ingestionapp/services/statute_scout.py) |
| `KIND_ORDINANCE`         | `ordinance`          | Not yet produced. Spec 016 deferred Denver ordinance ingestion to an as-yet-uncreated follow-on spec ("016.b" in spec 016's own next-gen notes); no ordinance-ingestion spec package exists today |
| `KIND_ORDINANCE_SECTION` | `ordinance_section`  | Not yet produced — same deferral as `KIND_ORDINANCE`                |
| `KIND_REGULATION`        | `regulation`         | Not yet produced — no regulation-ingestion spec exists today        |
| `KIND_DERIVED`           | `derived`            | Not yet produced — no spec currently writes `DerivedDocument`       |

Adding a new kind is a code-only change (no migration) thanks to `CharField(max_length=32)`.

## Implementation status

Spec-number cross-references drift as work lands under different spec slugs than originally planned, so treat this section as the authoritative shipped/declared split rather than the per-node "(spec NNN)" annotations above:

- **Shipped write paths**: `Case`/`Citation` (spec 001/002, [`queries.py`](../backend/law_ai/core/neo4j/queries.py)); `Jurisdiction`/`Code`/`Statute`/`StatuteSection` (spec 016, [`statute_queries.py`](../backend/law_ai/core/neo4j/statute_queries.py)).
- **Declared only (constraints/indexes exist; zero `MERGE` Cypher anywhere)**: `Court`, `Ordinance`, `OrdinanceSection`, `Regulation`, `DerivedDocument`, and the `CITES_STATUTE`/`INTERPRETS`/`DERIVED_FROM` edges.
- Retrieval (`graph_rag.py`, spec 028) reads `Case` and `StatuteSection` only — the other declared-only labels aren't retrievable even if someone wrote to them by hand.
