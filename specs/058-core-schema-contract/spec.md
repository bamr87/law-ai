# Spec: Core Schema Contract (Authority, Instrument, Action, GovernanceLink)

- **ID**: 058-core-schema-contract
- **Status**: draft
- **Owner**: @bamr87
- **Created**: 2026-11-13
- **Roadmap Epic**: [docs/core-schema.md](../../docs/core-schema.md) (implementation sequence, step 1) — the US-first foundation for [legal-ai-governance-framework.md](../../docs/legal-ai-governance-framework.md) Phase 1 (LAWAI-011) and Phase 6 (LAWAI-016); git as the eventual record is [ADR 0009](../../docs/adr/0009-git-record-store.md)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). §1: no model call and no new vendor; the contract is plain Pydantic and Cypher. §2: Pydantic v2 and the Neo4j driver are already locked in; no new dependency. §4: every new model extends `LegalProvenance`, and every graph write carries `source`, `source_url`, `confidence`, `ingest_timestamp` and `agent_version`; nothing is hard-deleted. §5: this is a schema migration, so `human_approval_required: true`, and only human-accepted records reach the graph. §12 I1: the graph writer added here is the single writer of the new labels and is reached only from an approval path, never directly from a Celery task. §13: answered in §2.

## 1. Problem & Motivation

The graph models law by corpus — `Case`, `StatuteSection`, `OrdinanceSection` — and has no model of the system that produces it. Nothing records who issued an instrument (`:Court` has a constraint and no writer), what authorities do (no node for a rulemaking step, an enforcement action or a settlement), or who oversees whom. `:Regulation` is declared and has never been written. Provenance says where a record came from but not when it was retrieved, which agent produced it, or which verdicts were passed on it. And the schema exists only as Python, so nothing outside the backend — the data repository [ADR 0009](../../docs/adr/0009-git-record-store.md) introduces, for one — can validate a record.

The core-schema loop in [docs/core-schema.md](../../docs/core-schema.md) needs one typed contract that the source adapters, the structuring and reviewer agents, and later the git record store all share. Without it, each of the next three specs (the Federal Register adapter, the Colorado Attorney General adapter and the review loop) would define its own shapes, and the milestone's exit criterion — the schema unchanged across two consecutive runs — could not even be measured.

## 2. Origin & Background

- Backlog items claimed: none — direct request (2026-11-13, review of the [original draft](../../docs/history/2026-11-core-schema-draft.md)). This spec files BL-20261114-07 for the relabelling it defers; the later steps of the sequence are BL-20261114-01 … BL-20261114-06 and BL-20261114-08 … BL-20261114-10.
- Prior art reused, not rebuilt: [spec 015](../015-legal-corpus-schema/spec.md) (the `Jurisdiction` … `DerivedDocument` labels, the `LegalProvenance` mixin in `backend/law_ai/core/schemas/legal_documents.py`, the `PendingReview.kind` discriminator); [spec 016](../016-ingest-colorado-statutes/spec.md) and BL-20260509-05 (the statute and ordinance write paths this mirrors); the Neo4j migration runner (`core/neo4j/migrator.py`, BL-20260509-02); `ingestionapp/services/approval.py` `_commit_by_kind`, the approval path every new kind joins; `core/reviewer.py` `ReviewerIdentity` for human verdicts; the `export_api_schema` command, whose generated-and-drift-tested pattern the JSON Schema export copies.
- Decisions of 2026-11-13 this spec encodes (from [docs/core-schema.md](../../docs/core-schema.md) § Decisions of record): the federal jurisdiction code is `us-federal`; individuals are never named in structured fields; Pydantic is the schema's source of truth and JSON Schema is generated from it; public-domain text is content-addressed; every record carries a semver `schema_version`; git becomes the record only after the first loop run, so this spec ships the quarantine-and-graph implementation of `RecordStore`.
- **Review question (constitution §13)** — *who is the stronger here, and what does this feature do for them?* The contract ranks and summarises nothing, but it decides what the platform can say about authority, so it can tilt the record. The stronger parties are the issuers who publish the most structured official material (a federal agency on the Federal Register's API, against a state Attorney General's HTML press releases) and the well-resourced organisations that appear in enforcement records as named, represented parties. A schema shaped by what is easy to parse would make their law look like the law. This contract answers with: mandatory attribution (no Instrument without `authority_id`, `jurisdiction_code` and a date; no Action without its authority); `confidence` documented and validated as the producer's confidence, never a measure of legal weight; `source_tier` recorded and labelled, never used as a filter; GovernanceLinks that cannot exist without a basis instrument; and individuals never named, so the burden of a structured public record falls on organisations that can contest it rather than on people who cannot.

## 3. Goals

- **G1**: One typed contract — Pydantic v2 models for Authority, Instrument, Action, GovernanceLink, OfficialSource and CommentPeriod, plus the record envelope, snapshot and status-history types — that extends spec 015 rather than forking it.
- **G2**: A machine-readable JSON Schema generated from those models, committed and drift-tested, for consumers outside the backend.
- **G3**: Graph constraints and indexes for the new labels, purely additive.
- **G4**: A `RecordStore` seam with a working implementation over the existing quarantine and graph, so the adapters and the loop can write before the git store exists.
- **G5**: The data model documented in [docs/data-model.md](../../docs/data-model.md).

## 4. Non-Goals

- **NG1**: Any source adapter or ingestion — the Federal Register and Colorado Attorney General adapters are BL-20261114-01 and BL-20261114-02.
- **NG2**: Agents or the review loop (BL-20261114-03). Nothing here calls a model.
- **NG3**: The git record store ([ADR 0009](../../docs/adr/0009-git-record-store.md), BL-20261114-04), which lands after the first loop run.
- **NG4**: Relabelling existing nodes — adding `:Instrument` to `Case`, `StatuteSection` and the rest, or `:Authority` to `Court` (BL-20261114-07). New labels go on new nodes only.
- **NG5**: Retrieval changes. `graph_rag.py` does not read the new labels in this spec.
- **NG6**: Agents as entities and the platform namespace — LAWAI-017.
- **NG7**: As-of-date (bitemporal) queries — LAWAI-016. This spec stores the history those queries will read.
- **NG8**: HTTP routes.

## 5. User Stories

- As the engineer building the Federal Register adapter, I want typed Instrument, Action and CommentPeriod models with provenance and a `RecordStore` to hand them to, so the adapter is parsing and mapping only.
- As the author of the reviewer agent, I want every record to carry its `source_url`, `source_tier`, citation and `basis_instrument_id` in validated fields, so every check is deterministic.
- As an operator triaging the quarantine, I want each new entity type under its own `PendingReview.kind`, so one admin filter shows me all pending Actions.
- As the maintainer of the future data repository, I want a JSON Schema file generated from the same models, so records are validated in CI without importing the backend.

## 6. Functional Requirements

- **FR-1**: A record envelope, `CoreRecord`, extends `LegalProvenance` with `retrieved_at` (datetime), `produced_by` (`<agent-name>@<version>`, pattern-validated), `reviewed_by` (list of `ReviewVerdict`: `reviewer`, `reviewer_kind` = `agent` | `human`, `verdict` = `accepted` | `rejected`, `reason`, `at`), `review_status` (`pending` | `accepted` | `rejected`), `source_tier` (`official` | `aggregator`) and `schema_version` (semver). `extra="forbid"`, as on `LegalProvenance`.
- **FR-2**: `Jurisdiction` gains an optional `parent_code`. Its `code` is validated against `^[a-z]{2}(-[a-z0-9]+)*$`, and the federal jurisdiction is `us-federal`. The existing `level` enum is unchanged.
- **FR-3**: `Authority(CoreRecord)` with `id` (`<jurisdiction>/authority/<slug>`), `name`, `jurisdiction_code`, `kind` (`legislature` | `court` | `agency` | `executive` | `independent-body`), `branch` (`legislative` | `judicial` | `executive` | `hybrid`), `parent_authority_id`, `powers` (subset of `legislating`, `rulemaking`, `adjudication`, `enforcement`, `investigation`, `guidance`, `licensing`) and `website`. A validator rejects a `kind` and `branch` that contradict each other (a `court` outside `judicial`, a `legislature` outside `legislative`).
- **FR-4**: `Instrument(CoreRecord)` with `id`, `title`, `kind` (`constitution` | `treaty` | `statute` | `bill` | `regulation` | `ordinance` | `case` | `court-rule` | `executive-order` | `guidance` | `policy` | `standard`), `authority_id`, `jurisdiction_code`, `citation`, `effective_date`, `status` (`proposed` | `final` | `in-force` | `stayed` | `withdrawn` | `repealed` | `vacated` | `expired`), `supersedes`, `amends`, `implements` (lists of instrument ids), `source_url` (required), `text_ref` (`sha256:<64 hex>` or an `https` URL), `snapshots` (list of `Snapshot`: `retrieved_at`, `source_url`, `content_hash`, `text_ref`) and `status_history` (list of `StatusChange`: `status`, `effective_date`, `basis_action_id`). When `status_history` is non-empty, its last entry's status must equal `status`.
- **FR-5**: `Action(CoreRecord)` with `id` (`<authority-id>/action/<source-native-id>`), `authority_id`, `kind` (`rulemaking` | `enforcement` | `settlement` | `ruling` | `guidance-issued` | `audit` | `investigation` | `legislation`), flat dates `announced_on`, `published_on`, `effective_on` (at least one required), `relies_on` and `produces` (instrument ids), `subjects` (list of `ActionSubject`: `kind` = `organization` | `government` | `individual` | `class` | `sector` | `instrument`, `name`, `ref_id`), `outcome` and `source_url` (required). A subject of kind `individual` with a `name` or `ref_id` is a validation error.
- **FR-6**: `GovernanceLink(CoreRecord)` with `id` (deterministic from `from_id`, `relation`, `to_id` and `basis_instrument_id`), `from_id`, `to_id`, `relation` (`reviews` | `funds` | `appoints` | `audits` | `appeals-to` | `delegates-to` | `reports-to` | `enforces` | `administers` | `preempts`), `basis_instrument_id` (required, non-empty) and `notes`.
- **FR-7**: `OfficialSource(CoreRecord)` with `source_id`, `authority_id`, `name`, `url`, `kind` (`rulemaking-docket` | `court-docket` | `opinions` | `register` | `guidance-page` | `press-releases`), `tier` (`official` | `aggregator`), `access` (`open` | `key` | `paid`), `poll_cadence` (`daily` | `weekly` | `on-event`), `parser` and `last_polled_at`.
- **FR-8**: `CommentPeriod(CoreRecord)` with `id` (`<action-id>/comment-period`), `action_id`, `opens`, `closes`, `docket_url`, `draft_ref` and `status` (`open` | `submitted` | `closed`). `closes` is documented as copied from the source exactly as published, never computed.
- **FR-9**: Every id in FR-3 … FR-8 is deterministic — derived from the source's own identifiers or from a hash of the defining fields, never random — so re-ingesting the same source document produces the same id.
- **FR-10**: A management command writes one committed JSON Schema document (a `$defs` entry per model) generated from the models with Pydantic's `model_json_schema`. A test regenerates it and fails on any difference, the same pattern as `export_api_schema`.
- **FR-11**: A forward-only Neo4j migration `009_core_schema.cypher` adds uniqueness constraints on `Authority.id`, `Instrument.id`, `Action.id`, `GovernanceLink.id`, `OfficialSource.id` and `CommentPeriod.id`, and range indexes on `Instrument.effective_date` and `Action.published_on`. Every statement is `IF NOT EXISTS`-guarded and Community-compatible.
- **FR-12**: Graph mapping. Accepted records are written as nodes with their scalar fields and id lists; nested lists (`reviewed_by`, `snapshots`, `status_history`) stay in the record store, and the node carries `latest_content_hash`, `review_status` and `source_tier` as scalars. New Instrument nodes carry `:Instrument` plus the matching existing label where one exists (`regulation` → `:Regulation`, `statute` → `:Statute`, `ordinance` → `:Ordinance`, `case` → `:Case`); Authority nodes of kind `court` also carry `:Court`. Relationships: `(:Authority)-[:IN_JURISDICTION]->(:Jurisdiction)`, `(:Authority)-[:PART_OF]->(:Authority)`, `(:Jurisdiction)-[:PART_OF]->(:Jurisdiction)`, `(:Instrument)-[:ISSUED_BY]->(:Authority)`, `(:Instrument)-[:IN_JURISDICTION]->(:Jurisdiction)`, `(:Instrument)-[:SUPERSEDES|AMENDS|IMPLEMENTS]->(:Instrument)`, `(:Action)-[:TAKEN_BY]->(:Authority)`, `(:Action)-[:RELIES_ON]->(:Instrument)`, `(:Action)-[:PRODUCES]->(:Instrument)`, `(:GovernanceLink)-[:FROM]->()`, `(:GovernanceLink)-[:TO]->()`, `(:GovernanceLink)-[:BASIS]->(:Instrument)`, `(:CommentPeriod)-[:FOR_ACTION]->(:Action)`, `(:OfficialSource)-[:SOURCE_OF]->(:Authority)`. An edge whose far end is not in the graph yet is not created; the id stays on the node for a later pass, exactly as an unresolved citation does today.
- **FR-13**: One `PendingReview.kind` per new entity type, added to `ingestionapp/quarantine_kinds.py` (code-only, no Postgres migration), and a `_commit_by_kind` branch for each that commits through the FR-14 writer.
- **FR-14**: A `RecordStore` protocol — put a pending record for a cycle, accept it with the verdicts, reject it with the verdicts, get by id, list a cycle's records — and one implementation, `QuarantineRecordStore`: pending records become `PendingReview` rows of their kind, and accepting a record (a human decision through the existing approval path) writes it to the graph through a single writer module for the new labels. Rejected records stay in the quarantine with their reasons. This writer is the only code that writes the new labels.
- **FR-15**: [docs/data-model.md](../../docs/data-model.md) documents the new labels, relationships, constraints and quarantine kinds in its existing table style; its federal jurisdiction example changes from `us-fed` to `us-federal`; [docs/core-schema.md](../../docs/core-schema.md) links the shipped models.

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: Every new model requires the constitution §4 fields; `confidence` is validated to `0 ≤ c ≤ 1` and its field description says it is the producer's confidence. Every node and edge the writer creates carries `source`, `source_url`, `confidence`, `ingest_timestamp` and `agent_version`.
- **NFR-HITL-1**: `human_approval_required: true` — this spec adds a schema migration (constitution §5). At runtime, a record reaches the graph only after a human accepts it; a `pending` or `rejected` record is never written to Neo4j.
- **NFR-MIGRATION-SAFETY-1**: Migration 009 is forward-only, idempotent and additive: no existing node, label, property or constraint is changed or removed.
- **NFR-PRIVACY-1**: No structured field of any model can hold an individual's name or identifier (FR-5 validator) — decision of 2026-11-13.
- **NFR-COMPAT-1**: Existing `LegalProvenance` payloads (the case, statute and ordinance paths) validate and commit unchanged; `CoreRecord`'s new required fields apply only to the new models.
- **NFR-SEC-1**: Every Cypher statement uses parameter binding; no value is interpolated into a query string.
- **NFR-TYPE-1**: Every new module is `mypy --strict` clean (it has no ratchet baseline entry, constitution §3).
- **NFR-OSS-1**: No new third-party dependency.

## 8. Data Model Impact

- **Neo4j** — new labels `Authority`, `Instrument`, `Action`, `GovernanceLink`, `OfficialSource`, `CommentPeriod`; the relationships in FR-12; migration `009_core_schema.cypher` (FR-11). Existing labels gain new nodes from this path (a `:Regulation` with `:Instrument`, a `:Court` with `:Authority`) but no existing node changes. Every new node carries the §4 provenance fields.
- **Postgres** — no schema change; new `PendingReview.kind` values only (the column is `CharField(32)`).
- **Files** — one generated JSON Schema document (FR-10).
- **Docs** — [docs/data-model.md](../../docs/data-model.md) (FR-15).

## 9. API Surface

None. No routes are added or changed, so the API contract fixture does not move.

## 10. Agent / Crew Impact

None. No agent is added or changed, and no model is called. The models and `RecordStore` are what the BL-20261114-01 and BL-20261114-02 adapters and the BL-20261114-03 agents will import.

## 11. Acceptance Criteria

- **AC-1**: A valid fixture for every model in FR-1 … FR-8 validates, and each of these raises `ValidationError`: `confidence=1.5`; a malformed `produced_by`; an Authority whose `kind` and `branch` contradict; an Instrument whose last `status_history` entry disagrees with `status`; an Action with no date; an Action subject of kind `individual` carrying a `name`; a GovernanceLink without `basis_instrument_id`; a `Jurisdiction` code of `US-Federal`.
- **AC-2**: The existing case, statute-section and ordinance-section payload fixtures validate and commit exactly as before (NFR-COMPAT-1).
- **AC-3**: Building the same source record twice produces the same id for every entity type (FR-9).
- **AC-4**: Regenerating the JSON Schema reproduces the committed file byte for byte, and the test fails when a model changes without regeneration (FR-10).
- **AC-5**: Every statement in `009_core_schema.cypher` is `IF NOT EXISTS`-guarded, and applying migrations 001–009 to a fresh Neo4j (integration) twice yields the constraints and indexes in FR-11 with no error on the second run.
- **AC-6**: Integration, against real Postgres and Neo4j: putting a pending record creates a `PendingReview` row of its kind and nothing in the graph; accepting it through the approval path writes the node, its labels and the FR-12 relationships whose far ends exist, each carrying the §4 provenance fields; rejecting another leaves the graph untouched and keeps the reasons on the row.
- **AC-7**: Accepting the same record twice creates zero duplicate nodes or relationships.
- **AC-8**: [docs/data-model.md](../../docs/data-model.md) documents every new label, relationship and quarantine kind, uses `us-federal`, and the repository's doc tests and `make lint-specs` pass.

## 12. LegalBench Impact

- Tasks affected: none — no reasoning path changes and nothing is retrieved from the new labels.
- Expected delta: 0 pp.

## 13. Risks & Open Questions

- **R-1** (med): Until BL-20261114-07 relabels the existing corpus, `:Instrument` covers new nodes only, and a query over it silently misses the statutes and cases already in the graph. Mitigation: retrieval does not read the new labels in this spec (NG5), and the data-model docs say so next to the label.
- **R-2** (med): The enums are drawn from US practice and will grow. Mitigation: `schema_version` on every record, forward-only changes, and the milestone's two-runs-unchanged criterion as the stability check.
- **R-3** (low): A reified `GovernanceLink` costs a hop on every oversight traversal compared with a typed relationship. Accepted because a link needs its own provenance, review state and history, which a relationship cannot carry as cleanly.
- **R-4** (low): Edges to entities not yet ingested are deferred (FR-12), so a fresh graph is sparse until both ends arrive. Mitigation: the ids stay on the node; the loop's structuring pass (BL-20261114-03) re-links.

> [OPEN QUESTION OQ-1]: Source documents can name individuals even though structured fields never do (a press release announcing a settlement with a named person). Should `Snapshot.text_ref` keep the verbatim official text — hash-verifiable against the source, never projected into the graph or returned by retrieval as structured data — or should text be redacted before storage, which breaks content-hash verification against the source? This is a privacy decision about what the platform retains, so it is the maintainer's call.

## 14. Out of Scope / Follow-ups

- Relabelling the existing corpus under `:Instrument` / `:Authority` — BL-20261114-07.
- The source adapters, the loop, the git store, snapshots-over-time and the feedback pipeline — BL-20261114-01 … BL-20261114-06.
- Feature-catalog ids for this work — BL-20261114-10.
- Retrieval over the new labels, with source tier and staleness labels in the coverage note — to be filed when the first milestone run shows what retrieval needs.
