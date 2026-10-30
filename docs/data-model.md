# Data Model

> The Neo4j knowledge-graph schema — nodes, relationships and mandatory provenance properties — and the Postgres quarantine that ingestion writes to.

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
| `holding_summary`   | string   | Optional; indexed by fulltext (mig 007). Populated at ingest by `derive_holding_summary` ([`scout.py`](../backend/law_ai/ingestionapp/services/scout.py)) with a deterministic first-substantive-paragraph excerpt of the opinion body, capped at 600 chars (`BL-20260810-19`). Nodes ingested before that change carry none; `make manage CMD='backfill_holding_summaries --refetch --commit'` ([`backfill_holding_summaries.py`](../backend/law_ai/ingestionapp/management/commands/backfill_holding_summaries.py)) re-fetches those opinions and writes the same excerpt an ingest would, write-once and read-only unless `--commit` (`BL-20260905-99`) |
| `holding_summary_kind` | string | Optional; `excerpt` (verbatim opinion text chosen by rule) or `summary` (written by an audited model pass — `IngestionScout.aextract` behind `INGEST_LLM_SUMMARY`, routed through `law_ai.core.llm` so the `llm_call` event is written, off by default and fail-open back to the excerpt, `BL-20260906-01`). GraphRAG passes it through as `snippet_kind` and `LegalWorkflow` labels excerpts in the prompt, so a syllabus header is never quoted as "the court held" |
| `aliases`           | string[] | Normalized citation forms (spec 002)   |
| `disposition`       | string   | Optional; one of `affirmed`/`reversed`/`remanded`/`dismissed`/`vacated`/`other`. Mapped deterministically from the source record's own disposition text by `map_disposition` ([`scout.py`](../backend/law_ai/ingestionapp/services/scout.py)); **null when the record is silent, and never inferred by an LLM** ([ADR 0004](adr/0004-jurisprudential-stance.md) P3, `BL-20260803-01`) |
| `prevailing_party_type` | string | Optional; one of `appellant`/`appellee`/`plaintiff`/`defendant`/`government`/`mixed`. Derived only where the disposition is structurally unambiguous (`affirmed` → appellee, `reversed` → appellant) on an appellate posture; null otherwise. A coarse *role*, never a named party |
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

### `Ordinance` / `OrdinanceSection` _(spec 015; write path `BL-20260509-05`)_

Same shape as `Statute` / `StatuteSection` but keyed on `jurisdiction_code` (e.g. `us-co-denver`) rather than `code_id` — a municipal code has no title layer, so the tree is `Jurisdiction ← Ordinance ← OrdinanceSection` with no `Code` node between them. `OrdinanceSection.text` is fulltext-indexed (mig 007).

Written by [`ordinance_queries.py`](../backend/law_ai/core/neo4j/ordinance_queries.py) from [`OrdinanceScout`](../backend/law_ai/ingestionapp/services/ordinance_scout.py), whose first (and so far only) source is the Denver Revised Municipal Code. Ids are `us-co-denver/dmc/chapter-38` and `us-co-denver/dmc/38-31`; sections cite as `D.R.M.C. § 38-31`.

`OrdinanceSection` carries one property its statute counterpart does not: `history_note`, the verbatim `(Ord. No. 342-05, § 1, 5-31-05)` trailer municipal codes print under each section. It is the amendment trail and the only pointer back to the enacting ordinance, so it is stored as printed rather than paraphrased; `effective_from` is parsed from the latest date in it.

Because the source requires human approval (see [data-sources.md](data-sources.md#license-and-access-posture)), every ordinance section is quarantined with `kind="ordinance_section"` and reaches the graph only through `approval._commit_by_kind` → `OrdinanceScout.commit_section`.

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

An ingest can only resolve a `Citation` against the cases that already existed when it ran, so the graph accumulates `HAS_CITATION` edges whose `CITES` counterpart was never created. `make densify-backfill` (the `densify_backfill` management command, [`backend/law_ai/ingestionapp/management/commands/densify_backfill.py`](../backend/law_ai/ingestionapp/management/commands/densify_backfill.py)) walks those pairs with a keyset cursor over `Case.id`, re-resolves each citation through `resolve_citations`, and MERGEs the missing `CITES` edge with the `confidence` carried by the existing `HAS_CITATION` edge. It is read-only unless `--commit` (`COMMIT=1`) is passed, never writes `:Case` properties, and is safe to re-run.

### Statutory / regulatory _(spec 015)_

- `(:StatuteSection)-[:PART_OF]->(:Statute)`
- `(:Statute)-[:PART_OF]->(:Code)`
- `(:OrdinanceSection)-[:PART_OF]->(:Ordinance)`
- `(:Code|:Statute|:Ordinance|:Regulation|:Court)-[:IN_JURISDICTION]->(:Jurisdiction)` — declared for all five; `Code` and `Statute` are written by [`statute_queries.py`](../backend/law_ai/core/neo4j/statute_queries.py) and `Ordinance` by [`ordinance_queries.py`](../backend/law_ai/core/neo4j/ordinance_queries.py) (`BL-20260509-05`). `Regulation` and `Court` still have constraints/indexes only — no `MERGE` for either exists anywhere in the codebase.

### Temporal _(spec 015)_

- `(:StatuteSection)-[:AMENDS]->(:StatuteSection)`
- `(:StatuteSection)-[:SUPERSEDES]->(:StatuteSection)`

### Cross-corpus reasoning _(spec 015)_

- `(:Case)-[:CITES_STATUTE {confidence, source, ingest_timestamp}]->(:StatuteSection)` — **shipped** (`BL-20260509-07`)
- `(:Case)-[:INTERPRETS {confidence}]->(:StatuteSection)` — declared only, no write path

`CITES_STATUTE` is written by [`MERGE_CITES_STATUTE_CYPHER`](../backend/law_ai/core/neo4j/queries.py) from two places, both of which merge the edge only when the `:StatuteSection` already exists — an unresolved statutory cite leaves a `:Citation` node and no edge, exactly as an unresolved case cite does:

1. **At ingest**, `citation_resolver.densify_statute_extraction` maps each extracted citation string onto a candidate `StatuteSection.id` (`statute_section_id_from_normalized`, driven by the `STATUTE_CORPORA` table in [`citation_resolver.py`](../backend/law_ai/core/neo4j/citation_resolver.py) — CRS is its only entry today, because CRS is the sole statutory corpus in the graph; a second corpus is one table entry plus the ingest that writes its nodes, and the backfill's scan vocabulary (`STATUTE_REPORTERS`) follows it automatically, `BL-20260906-02`), verifies it in one Cypher round-trip, and `commit_extraction` merges the edge. Opinions that cite no statutes issue no extra query.
2. **Retroactively**, `make manage CMD='resolve_statute_citations --commit'` ([`resolve_statute_citations.py`](../backend/law_ai/ingestionapp/management/commands/resolve_statute_citations.py)) walks historical `:Case` nodes with a keyset cursor and does the same over the `Citation.normalized` strings earlier ingests already stored. `:Case` nodes do not persist opinion text, so the backfill reads those strings rather than re-fetching opinions upstream. Read-only unless `--commit`; edges it writes carry `source = "resolve_statute_citations_backfill"` so an auditor can tell them from ingest-time edges.

That second path has a recall limit worth stating plainly, and the command prints it on every run (`RECALL_CAVEAT`): it can only link citations an earlier ingest actually *stored*. Opinions ingested before the C.R.S. patterns in `scout._CRS_CITATION_RES` landed were scanned by eyecite alone, which recognises `Colo. Rev. Stat.` but yields a bare `UnknownCitation('§')` for `C.R.S. § 18-3-102` and nothing for `section 13-80-102, C.R.S.` — the two forms Colorado courts actually write. Those cases hold no C.R.S. citation string to resolve, so recovering them means reading the opinion again: `--refetch` (`BL-20260906-88`) walks the cases that carry *no* statutory citation at all, re-reads each opinion from its source, runs today's extractor over it, and merges what resolves — edges it writes carry `source = "resolve_statute_citations_refetch"`, distinct from the offline pass. Only corpora with a per-document upstream endpoint qualify (`REFETCHABLE_SOURCES`); everything else still needs a re-ingest. Without `--refetch`, a clean backfill summary means "nothing visible offline", not "nothing left to link".

`INTERPRETS` remains deferred: deciding that an opinion *construes* a section, rather than merely citing it, is a judgement call the rule-based extractor cannot make.

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

## Cypher migrations

`backend/law_ai/core/neo4j/migrations/*.cypher` are applied by `python manage.py migrate_neo4j` (run by `make migrate` and by `backend/scripts/init-db.sh`), not by a `cypher-shell` loop. The runner ([`core/neo4j/migrator.py`](../backend/law_ai/core/neo4j/migrator.py)) strips `//` comments, splits each file on `;`, runs every statement in its own auto-commit transaction (schema DDL cannot share a transaction with writes), and then records the file as `(:_Migration {id, applied_at, checksum, statement_count})`. A recorded migration is never re-run, which is what makes a non-idempotent migration — a data back-fill, say — safe to add; before this, `IF NOT EXISTS` was the only safety net (BL-20260509-02). Editing an already-applied file is reported as a checksum mismatch and skipped rather than failing the run: add a new migration instead. `migrate_neo4j --list` shows what is applied and what is pending; `--dry-run` reports without writing.

One nuance the runner surfaces rather than hides: `006_derived_document` declares property-existence constraints, which are Enterprise-only, and the pinned `neo4j:5-community` image rejects them. Those statements are reported as unsupported and the file is left pending, so it applies in full the first time it meets an Enterprise database. The `cypher-shell` loop it replaced simply failed there.

## Embeddings and the vector index

`:Case` and `:StatuteSection` carry an `embedding` (plus `embedding_model` and `embedding_at`) produced by `nomic-embed-text` through [`core/llm/embeddings.py`](../backend/law_ai/core/llm/embeddings.py). The embedder is pinned to the local Ollama endpoint regardless of `LLM_PROVIDER_CHAIN`: a vector index is only coherent when every vector in it came from the same model, and keeping it local also keeps LegalBench numbers comparable and ingest free of a per-document vendor cost. It is fail-open — an unreachable embedder means the node is committed without a vector, never a failed ingest.

`008_vector_indexes.cypher` declares `case_embedding_vec` and `statute_section_embedding_vec` (768 dimensions, cosine), which must match `EMBED_DIMENSIONS`; changing the embedding model means a new migration plus a re-backfill, never an edit to 008. `make backfill-embeddings COMMIT=1` fills historical nodes. The retriever fuses the vector top-K with its lexical top-K by reciprocal-rank fusion before citation expansion (BL-20260810-17) — once per label, so a `:StatuteSection` hit is never crowded out by a `:Case` one — and when the index or the embedder is missing it skips the leg and says so in its coverage note.

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
| `reviewer_user` | FK to user, optional | The deciding Django account when one was signed in (BL-20260811-04); `SET_NULL` so deleting a user never erases the decision |
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
| `KIND_ORDINANCE`         | `ordinance`          | Declared for the discriminator; not actually produced — like `KIND_STATUTE`, `OrdinanceScout` commits the chapter anchor alongside an approved section rather than quarantining at the chapter level |
| `KIND_ORDINANCE_SECTION` | `ordinance_section`  | `OrdinanceScout` (`BL-20260509-05`) — shipped, [`ordinance_scout.py`](../backend/law_ai/ingestionapp/services/ordinance_scout.py). **Every** section arrives here: the Denver source requires human approval, so this is not the exception path but the only path |
| `KIND_REGULATION`        | `regulation`         | Not yet produced — no regulation-ingestion spec exists today        |
| `KIND_DERIVED`           | `derived`            | Not yet produced — no spec currently writes `DerivedDocument`       |

Adding a new kind is a code-only change (no migration) thanks to `CharField(max_length=32)`.

## LSAT proposal queue _(Postgres, BL-20260527-05)_

The LSAT HITL queue is an append-only JSONL log — `backend/var/lsat_proposals/proposals.jsonl`, replayed per read by [`lsat/services/proposals.py`](../backend/law_ai/lsat/services/proposals.py) — with an indexed Postgres mirror of the *current* state in `law_ai.lsat.models.LsatProposal`. The log remains the audit trail and the source of truth for replay: every write appends there first and then refreshes the mirror row best-effort, so a database that is down or unmigrated degrades to the replay rather than blocking a reviewer.

| Field                                       | Type                                | Notes                                                                     |
| ------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------- |
| `id`                                        | text (PK)                           | `prop-<hex12>`, minted by `record_proposal`                                |
| `proposal_kind`                             | `CharField(32)`, indexed            | `question` · `guide` · `library_finding` · `library_article` · `crosscheck` |
| `status`                                    | `CharField(16)`, indexed            | `pending` · `approved` · `rejected`                                        |
| `section` / `difficulty`                    | text                                | Denormalised from the draft for filtering                                  |
| `agent_trace_id` / `model` / `confidence`   | text / text / float                 | Producer lineage (spec 019 FR-4)                                           |
| `reviewer` / `note`                         | text, `reviewer` indexed            | The HITL decision's identity + rationale (BL-20260810-08)                  |
| `question_id`                               | text, indexed                       | Bank id assigned on promotion                                              |
| `created_at` / `updated_at`                 | datetime, `created_at` indexed      | Composite index on `(status, -created_at)` for the queue listing           |
| `payload`                                   | JSON                                | The replayed row verbatim, so the API shape is store-independent           |

Reads only prefer the table when `LSAT_PROPOSALS_DB_READS=true`, and only when the table is non-empty: a mirror that predates `manage.py lsat_proposals_backfill` would otherwise hide older proposals. Async callers never touch the ORM (Django's ORM is sync-only) and fall back to the replay.

## Persisted analyses _(Postgres, BL-20260429-25)_

An Analysis Studio run used to exist only as a JSONL provenance trail plus whatever the browser still had in memory. `law_ai.analysis.models.AnalysisRun` keeps the user-facing artefact so a run is addressable at `GET /api/analysis/<analysis_id>` and the Studio permalink (`/analysis?id=…`) survives a refresh.

| Field                                    | Type                          | Notes                                                                        |
| ---------------------------------------- | ----------------------------- | ---------------------------------------------------------------------------- |
| `analysis_id`                            | text (PK)                     | `an-<hex12>`, the id the API already minted for the response and WS group      |
| `request` / `response`                   | JSON                          | The validated `AnalysisRequest` and the finished `AnalysisResponse`            |
| `trace_id`                               | text, indexed                 | Parent `AnalysisStudio` provenance trace                                       |
| `child_trace_ids`                        | JSON (list)                   | The agent traces the run fanned out to — the `/api/agents/runs/{trace_id}` join |
| `engine`                                 | `CharField(32)`               | `langgraph` · `direct`                                                         |
| `confidence` / `requires_human_review`   | float / bool                  | Denormalised from the response for listing without parsing JSON                |
| `created_by`                             | FK user, `SET_NULL`           | The signed-in owner when there is one (spec 036 FR-2); null for key-only runs   |
| `created_at` / `archived_at`             | datetime                      | Soft-delete only: an archived run is a 404, never a deleted row                 |

The write is best-effort and happens after the response is built: an analysis that already ran must not turn into a 500 because Postgres blinked, so a failure is logged and the caller still gets the answer. The JSONL audit log remains the record of what happened; this table is the artefact.

## Autonomy runs _(Postgres, BL-20260511-04)_

Every autonomy cycle has always emitted paired `autonomy_cycle.start` / `autonomy_cycle.end` `audit.AuditEvent` rows, and still does — the audit layer is never bypassed (constitution §4). But a generic `kind`/`payload` pair answers "what ran at 03:00 and how did it end" only by unpacking JSON in Python, so the digest's single `kind__startswith='autonomy_'` window filter was the *only* query the data supported. `law_ai.audit.models.AutonomyRun` is the promoted, queryable projection of the same cycles.

| Field                     | Type                    | Notes                                                                     |
| ------------------------- | ----------------------- | ------------------------------------------------------------------------- |
| `cycle_id`                | text, indexed           | The id shared with this run's provenance events — row and trail join on it |
| `kind`                    | text, indexed           | `corpus_growth` · `digest` · `lsat_*` · … (`test_pillar` rows predate ADR 0008)                   |
| `source`                  | text                    | Adapter name for `corpus_growth`; blank otherwise                          |
| `started_at` / `ended_at` | datetime                | `started_at` is indexed and is what the digest window filters on           |
| `status`                  | `CharField(16)`         | `ok` · `error` · `disabled` · `replayed`                                    |
| `duration_ms`             | float                   | Wall time of the runner; `0` for a cycle that never ran one                |
| `error`                   | text                    | `repr()` of the uncaught exception on a failed cycle                       |
| `summary`                 | JSON                    | The cycle context minus the columns above: counts, digest path, result     |

Composite index on `(kind, -started_at)` — "the last N runs of this pillar" is the query both the digest and the dashboard make.

Writes are **best-effort**: `run_cycle` logs and continues when the insert or the closing save fails, so a Postgres outage degrades a report rather than killing a cycle. That is the same never-block contract `compose_digest` has, and it is why the `autonomy_cycle.*` events remain the record of what happened while this table is the queryable projection.

`compose_digest` reads `summary` as well as the columns (`BL-20260906-22`): recognised keys (`prs_opened`, `backlog_ids`, `quarantined`, `legalbench_delta`, at the top level or under `result`) are folded into the digest's four content sections, and the numeric counts a runner reported ride on its cycle line. The `AuditEvent` scan stays alongside it — legacy windows predate the table — and entries an event already contributed are not repeated.

## Share links _(Postgres, BL-20260429-26)_

`law_ai.analysis.models.ShareLink` is one slug pointing at one `AnalysisRun`. `slug` is the primary key: a minted slug is `secrets.token_urlsafe(32)`, or a validated readable slug the owner chose (`^[a-z0-9][a-z0-9_-]{2,63}$`). `analysis` is a `CASCADE` FK, `created_by` a `SET_NULL` FK to the minting user, and `revoked_at` is the only way a link dies — the row is never deleted, so a revoked slug stays taken and cannot be re-minted by anyone else. `AnalysisRun.shareable` (default from `ANALYSIS_SHAREABLE_DEFAULT`) is the per-run kill switch: false means no slug can ever be minted and every existing one stops resolving.

## Setting values _(Postgres, BL-20260830-07)_

`law_ai.core.SettingValue` stores the shell's setting overrides server-side: `(scope_type, scope_id, key)` is unique, `value` is JSON, `locked` marks an override descendants may not shadow, and `updated_by`/`updated_at` record who last touched it. `scope_id` is the frontend's opaque identifier (`instance:local`, `user:<pk>`), so the two ends agree on identity without the backend modelling an org tree it does not have. Precedence and locking are resolved entirely in TypeScript (`frontend/lib/scope/resolver.ts`); this table only decides which rows exist and who may write them.

## LSAT attempt history _(Postgres, BL-20260503-05)_

`law_ai.lsat.models.LsatAttempt` is one graded answer by a signed-in learner: `user` (CASCADE — study history is the learner's own data, not an audit record), `question_id`, `section`, `difficulty`, `choice`, `correct`, `hints_used`, `shuffled`, `concepts` (JSON) and `created_at`, indexed on `(user, -created_at)` and `(user, question_id)`. The `lsat_grade` audit event is still written for every attempt, signed-in or not, so the anonymous path is unchanged; this table is what lets `GET /api/lsat/stats` answer per learner instead of per instance. `law_ai.lsat.services.attempts` aggregates it: totals, per-section buckets, an equal-count accuracy trend, and a Leitner review queue (box = the current streak of correct answers, due `2^(box-1)` days after the last attempt, a miss resets to box 0 and is due immediately). The response carries `scope: "user" | "instance"` so a client can tell which reading answered.

`law_ai.lsat.models.LsatWritingAttempt` is the same idea for the Argumentative Writing section (BL-20260906-18): `user` (CASCADE), `prompt_id`, `rubric_id`, `weighted_band` (nullable — a degraded evaluation happened and must not be recorded as a zero), `criteria` (JSON, `{criterion_id: band}`), `response_chars`, `model`, `prompt_version`, `degraded` and `created_at`, indexed on `(user, -created_at)`. A sibling table rather than a `section="WS"` row on `LsatAttempt`: an essay has no choice and no correct answer, the writing section is unscored, and folding a model-derived band into the accuracy denominator or the review queue would misreport both. The `lsat_writing_evaluate` audit event is still written for every evaluation, so the anonymous reading of `/api/lsat/stats` is unchanged; a signed-in learner's `writing` block now comes from this table instead of the instance-wide tail.

`law_ai.lsat.models.LsatArticleRead` is the durable projection of library reading progress (BL-20260905-39): `reader` (the string `"user:<pk>"` or `"instance"` — an anonymous deployment-wide reader has no user row to point at), `article_id`, `read`, `sections` (JSON), `kind`, `created_at`, `updated_at`, unique on `(reader, article_id)` and indexed on `(reader, read)`. Read state used to be replayed out of the bounded JSONL audit tail on every request, so an article whose `lsat_article_read` event had rotated out of the log silently un-marked itself. The event is still written first and remains the audit trail; `law_ai.lsat.services.reading` upserts this row beside it and overlays it on the replay, so the table wins where the two disagree and an unreachable table degrades to exactly the old behaviour. Un-marking writes `read=False` rather than deleting the row (constitution §4).

## Matters _(Postgres, spec 036 / BL-2026081x)_

`law_ai.matters` is the user-owned spine the legal journey hangs off. `Matter` carries `slug` (unique **per owner**, never globally), `name`, `description`, `issue_tags` (JSON), `jurisdiction`, `stage` (intake → research → analysis → action → review), `owner` and `archived_at`. `owner` is `PROTECT` on purpose: deleting a user must not cascade away the matters that give every audit row its context, so account deletion has to go through `law_ai.core.accounts.deletion`, which archives the matters and reassigns them to a tombstone account first. Every API lookup filters by `owner=request.user`, so another user's slug is a plain 404 — indistinguishable from one that never existed.

Three children hang off it. `MatterArtifact` (kind note/analysis/research/draft/document) stores what the work produced plus the `trace_id` and `analysis_id` that join it back to the audit log and to `AnalysisRun`. `MatterAuthority` records the cases and statute sections the matter relies on; `verified_at`/`verified_by` are the HITL gate, and only verified rows enter the GraphRAG boost set (`matters/services/authorities.py`, BL-20260817-05) — an unverified candidate never gets a ranking advantage. Recording one now checks `node_id` against the graph (`queries.AUTHORITY_NODE_EXISTS_CYPHER`, MATCH-only, archived nodes excluded): a node the corpus does not hold is refused with a 422, so an export bundle cannot cite an authority that does not exist, while an unreachable Neo4j degrades the check to `graph_labels: null` rather than blocking the reviewer (`BL-20260906-16`). `MatterArtifact.analysis_id` remains a string join to `AnalysisRun` rather than a FK. `MatterTask` holds the action stage's dated work: `due_at` is user-entered (spec 036 NG1 — nothing computes a court deadline from a rule of procedure), `reminded_at` makes the hourly reminder sweep idempotent, and `status`/`completed_at` close it out. Everything soft-deletes with `archived_at`.

## Implementation status

Spec-number cross-references drift as work lands under different spec slugs than originally planned, so treat this section as the authoritative shipped/declared split rather than the per-node "(spec NNN)" annotations above:

- **Shipped write paths**: `Case`/`Citation` (spec 001/002, [`queries.py`](../backend/law_ai/core/neo4j/queries.py)); `Jurisdiction`/`Code`/`Statute`/`StatuteSection` (spec 016, [`statute_queries.py`](../backend/law_ai/core/neo4j/statute_queries.py)); the `CITES_STATUTE` edge between them (`BL-20260509-07`, `MERGE_CITES_STATUTE_CYPHER` in [`queries.py`](../backend/law_ai/core/neo4j/queries.py)); `Ordinance`/`OrdinanceSection` (`BL-20260509-05`, [`ordinance_queries.py`](../backend/law_ai/core/neo4j/ordinance_queries.py)).
- **Declared only (constraints/indexes exist; zero `MERGE` Cypher anywhere)**: `Court`, `Regulation`, `DerivedDocument`, and the `INTERPRETS`/`DERIVED_FROM` edges.
- Retrieval (`graph_rag.py`, spec 028) reads `Case` and `StatuteSection` only — the other declared-only labels aren't retrievable even if someone wrote to them by hand.
