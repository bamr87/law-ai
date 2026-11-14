# Core Schema

> The shared contract for Law AI's model of the legal system — jurisdictions, authorities, instruments, actions and governance links — and for the agent loop that ingests, structures and reviews them, with the specs that implement it.

- **Status**: proposed (design of record; implemented spec by spec, see [Implementation sequence](#implementation-sequence))
- **Owner**: @bamr87
- **Created**: 2026-11-13, from the [original draft](history/2026-11-core-schema-draft.md) after review
- **Decision records**: [ADR 0009](adr/0009-git-record-store.md) (git as the record); [constitution.md](constitution.md) §1, §4, §5, §12, §13 (unchanged — this design fits inside them)
- **Epic**: the US-first foundation for [legal-ai-governance-framework.md](legal-ai-governance-framework.md) Phase 1 (LAWAI-011, norm taxonomy) and Phase 6 (LAWAI-016, temporal validity); the platform's own governance as an instance of the model is Phase 7 (LAWAI-017)

One contract for both the legal-system data and the agent harness that produces it. Every record the loop writes validates against it; change the contract first ([spec 058](../specs/058-core-schema-contract/spec.md) owns the Pydantic models), then everything downstream.

## Design principles

- Model the legal system as it operates: jurisdictions, the authorities within them, the instruments those authorities issue, the actions they take, and the oversight relationships between them.
- Build on what shipped. [Spec 015](../specs/015-legal-corpus-schema/spec.md) already defines `Jurisdiction`, `Court`, `Code`, `Statute`, `StatuteSection`, `Ordinance`, `Regulation`, `Case` and the `LegalProvenance` mixin; this contract generalises them rather than forking them. New nodes carry an extra label (`:Instrument:Regulation`, `:Authority:Court`); existing nodes are not relabelled until a separate, human-approved migration does it.
- Every record is traceable: source, retrieval time, jurisdiction, the agent that produced it, and every verdict passed on it.
- Pending is never in the graph. A record under review lives in the quarantine (today) or on a run branch of the data repository (after [ADR 0009](adr/0009-git-record-store.md) lands). Retrieval only ever reads accepted records, and labels the ones awaiting re-review instead of hiding them.
- Agents verify, humans decide. Agent verdicts are advisory; acceptance into the record is a human act (constitution §5, §12 I1).
- Start narrow: `us-federal` and `us-co`, two authorities, one loop end to end. Widen only after the loop reconciles cleanly.

## Decisions of record

| Date | Decision | Where it binds |
|---|---|---|
| 2026-11-13 | The federal jurisdiction code is `us-federal` (the `us-fed` example in [data-model.md](data-model.md) changes with spec 058; nothing in code writes either today). | spec 058 |
| 2026-11-13 | Git is the record for the core-schema layer. It lands **after** the first loop run; until then the loop writes through the `RecordStore` interface into the existing quarantine and graph. | [ADR 0009](adr/0009-git-record-store.md) |
| 2026-11-13 | Individuals are never named. An action directed at a person records `kind: individual` with no name and no identifying field; organisations and governments are named as the source names them. | spec 058 (validator) |
| 2026-11-13 | Comment-period close dates are copied from the source exactly as published (for example the Federal Register's `comments_close_on`), never computed, and may be copied into a matter task's due date with the source attached. | feedback-pipeline spec |
| 2026-11-13 | Pydantic v2 is the schema's source of truth; JSON Schema is generated from it for non-Python consumers and never hand-edited. | spec 058 |
| 2026-11-13 | Public-domain official text is stored content-addressed (`text_ref = sha256:<hex>`); restricted-licence sources keep an external reference only. | spec 058, ADR 0009 |
| 2026-11-13 | Every record carries a semver `schema_version`; schema changes are forward-only migrations validated against every record before merge. | spec 058 |

## Entity types

### Jurisdiction

A territory and level of government whose law applies. Existing label, keyed on `code`.

- `code` — stable slug: `us-federal`, `us-co`, `us-co-denver`
- `name`
- `level` — `federal` | `state` | `municipal` | `tribal` | `international` (the existing spec 015 enum; `municipal`, not `local`)
- `parent_code` — the enclosing jurisdiction, if any
- `notes`

The level names come from US practice. The epic's Phase 1 guardrail (no US or EU default) applies when the model widens: the enum grows, it is not reinterpreted.

### Authority

A body that makes, interprets or enforces law within a jurisdiction. Generalises the existing `:Court` (which gains the `:Authority` label when written through this contract).

- `id` — `<jurisdiction>/authority/<slug>`, e.g. `us-co/authority/attorney-general`
- `name`, `jurisdiction_code`, `website`
- `kind` — `legislature` | `court` | `agency` | `executive` | `independent-body`
- `branch` — `legislative` | `judicial` | `executive` | `hybrid` (validated for consistency with `kind`)
- `parent_authority_id` — the body above it in its own hierarchy (district court → appellate court)
- `powers` — any of `legislating` | `rulemaking` | `adjudication` | `enforcement` | `investigation` | `guidance` | `licensing`

### Instrument

A written source of law or quasi-law. Existing labels (`Statute`, `StatuteSection`, `Ordinance`, `Regulation`, `Case`) are instrument kinds; new instruments carry `:Instrument` plus the matching kind label where one exists.

- `id` — derived from the source's own identifier, e.g. `us-federal/fr/<document-number>`; existing ids keep their shape (`us-co/crs/18-3-102`)
- `title`, `citation`, `authority_id`, `jurisdiction_code`, `source_url`, `text_ref`
- `kind` — `constitution` | `treaty` | `statute` | `bill` | `regulation` | `ordinance` | `case` | `court-rule` | `executive-order` | `guidance` | `policy` | `standard`
- `status` — `proposed` | `final` | `in-force` | `stayed` | `withdrawn` | `repealed` | `vacated` | `expired` (`final` = published but not yet effective; `stayed` covers a court-ordered stay or injunction)
- `effective_date`
- `supersedes`, `amends`, `implements` — lists of instrument ids. Amendment is a relationship, not a status: an amended instrument is usually still in force.
- `snapshots[]` and `status_history[]` — see [Versioning](#versioning-and-reconciliation-over-time)

### Action

A discrete event in which an authority does something: a rulemaking step, an enforcement action or settlement, a ruling, an audit. No node models this in the graph today.

- `id` — `<authority-id>/action/<source-native-id>`
- `authority_id`, `source_url`, `outcome`
- `kind` — `rulemaking` | `enforcement` | `settlement` | `ruling` | `guidance-issued` | `audit` | `investigation` | `legislation`
- `announced_on`, `published_on`, `effective_on` — at least one; flat fields because graph properties cannot be maps
- `relies_on` — instrument ids the action relies on (the statute an enforcement action invokes)
- `produces` — instrument ids the action produces (the rule a rulemaking publishes)
- `subjects[]` — `{kind, name, ref_id}` where `kind` is `organization` | `government` | `individual` | `class` | `sector` | `instrument`. For `individual`, `name` and `ref_id` must be empty (decision of 2026-11-13).

### GovernanceLink

The oversight relationship between two entities — where accountability, review and AI-governance obligations live. Stored as its own node (`:GovernanceLink` with `FROM`, `TO` and `BASIS` relationships), because a link needs its own provenance, review state and history.

- `id` — deterministic from its defining fields, never random
- `from_id` (the overseeing entity), `to_id` (the overseen entity), `notes`
- `relation` — `reviews` | `funds` | `appoints` | `audits` | `appeals-to` | `delegates-to` | `reports-to` | `enforces` | `administers` | `preempts`
- `basis_instrument_id` — **required**: the instrument that establishes the relationship. A link without a basis is not a record.

A link a model infers from text goes to the quarantine with its confidence, like every other model-derived judgement in this repo ([ADR 0004](adr/0004-jurisprudential-stance.md) keeps `disposition` and `INTERPRETS` out of model hands for the same reason).

### OfficialSource

Where an authority is read from.

- `source_id`, `authority_id`, `name`, `url`, `parser`, `last_polled_at`
- `kind` — `rulemaking-docket` | `court-docket` | `opinions` | `register` | `guidance-page` | `press-releases`
- `tier` — `official` (published by the government body itself, e.g. the Federal Register) | `aggregator` (a faithful re-publisher, e.g. CourtListener, Justia)
- `access` — `open` | `key` (e.g. regulations.gov's api.data.gov key) | `paid` (e.g. PACER)
- `poll_cadence` — `daily` | `weekly` | `on-event`

The new Authority/Action layer reads `official` sources only. The existing corpus comes from aggregators and stays: every record carries its source tier and retrieval shows it. Constitution §13 is the rule — label, do not filter.

### CommentPeriod

- `id` — `<action-id>/comment-period`
- `action_id`, `opens`, `closes`, `docket_url`, `draft_ref`
- `status` — `open` | `submitted` | `closed`

`closes` is copied from the source exactly as published and never computed (decision of 2026-11-13).

## The record envelope

Every new record extends the existing `LegalProvenance` mixin (constitution §4) — one envelope, not a parallel one.

| Field | Origin | Meaning |
|---|---|---|
| `source`, `source_url`, `confidence`, `ingest_timestamp`, `agent_version` | spec 015 | unchanged; `confidence` is the producer's confidence, never a measure of legal weight |
| `retrieved_at` | new | when the source was fetched (`ingest_timestamp` is when the record was emitted) |
| `produced_by` | new | `<agent-name>@<version>` |
| `reviewed_by[]` | new | one verdict per reviewer: `{reviewer, reviewer_kind: agent \| human, verdict, reason, at}` — the agent's advisory verdict and the human decision both appear |
| `review_status` | new | `pending` \| `accepted` \| `rejected` — `pending` exists only in the quarantine or on a run branch |
| `source_tier` | new | `official` \| `aggregator`, copied from the OfficialSource |
| `schema_version` | new | semver of this contract |

Nested lists (`reviewed_by`, `snapshots`, `status_history`) live in the record store. The graph projects scalars and id lists, plus `latest_content_hash` and `needs_rereview_since` for retrieval to label.

## Agent roles and the loop

Each role works on one Authority at a time. The loop runs through `law_ai.core.autonomy.run_cycle()` behind `AUTONOMY_ENABLED`, and its sources are adapters in `SOURCE_REGISTRY` named in `AUTONOMY_ALLOWED_SOURCES` (constitution §12 I2–I4).

1. **Ingestion** — the source adapter for the Authority pulls recent Instruments and Actions from its official sources and emits raw records with `review_status: pending`. Deterministic; no model.
2. **Structuring** — fits raw records to the schema, resolves ids, links `supersedes` / `amends` / `implements`, and proposes GovernanceLinks. Deterministic first; a model is used only to propose links, and every model-proposed link is quarantined with its confidence.
3. **Review** — the appellate role, and deterministic: every `source_url` resolves and its content hash is recorded; every citation parses with the parser for its kind (FR, CFR, C.R.S., CCR, case reporters); every link names a basis that exists. Its verdict is advisory.
4. **Reconciliation** — a record the reviewer rejects returns to structuring with the reason attached, up to three times; then it goes to a human with the reasons.
5. **Human decision** — a person accepts or rejects the batch (scoped bulk approval exists already: `review_queue approve-all --id-prefix …`). Only then does a record reach the graph — and, after ADR 0009 lands, the run branch merges.

Agents can themselves be modelled with these types (the reviewer as an Authority, `reviews` as a GovernanceLink). That is LAWAI-017's worked example. It lives in a separate namespace that retrieval never reads, so an agent is never cited as legal authority.

## First milestone

- Jurisdictions: `us-federal`, `us-co`.
- Authorities: the Colorado Attorney General (rulemaking and enforcement authority under SB24-205, among others) and one federal agency with AI-governance activity, chosen when its source spec is clarified by checking the Federal Register for the window.
- One full ingestion → structuring → review → reconciliation loop over the last 90 days of Actions, written through `RecordStore` into the quarantine and graph. The git record store follows the first run.
- Exit criteria:
  - every record in the batch has a human decision (accepted, or rejected with a reason), and none is left pending;
  - zero broken `source_url` at review time, each with a stored content hash;
  - the same `schema_version` and generated-schema hash across two consecutive runs;
  - an `llm_call` audit event for every model call the run made, and `produced_by` / `reviewed_by` on every record.

## Versioning and reconciliation over time

Records are never overwritten. Each Instrument and Action keeps a history, so the platform can show what the law was on any date.

- `snapshots[]` — `{retrieved_at, source_url, content_hash, text_ref}`
- `diff_from_previous` — a deterministic diff; any model-written summary of it is labelled as one
- `status_history[]` — `{status, effective_date, basis_action_id}` (e.g. `proposed → final → in-force → vacated`)

Reconciliation runs after every poll:

1. **Detect** — compare the new snapshot's hash with the last.
2. **Classify** — a change triggers a status re-evaluation (new final rule, amendment, repeal, vacatur, stay, appeal decided).
3. **Propagate** — downstream records that `implements`, `supersedes`, `amends` or are governed by the changed one get `needs_rereview_since`, to a bounded depth. They stay retrievable, labelled as awaiting re-review.
4. **Re-review** — the reviewer re-runs on the flagged set. A conflict between two official sources goes to a human with both snapshots.

Full as-of-date querying (bitemporal validity) is LAWAI-016's scope; this layer supplies the history it will query.

## Feedback pipeline

New developments flow to an analysis agent that produces something a person can act on.

- **Triggers** — a new rulemaking Action with an open comment period, a new ruling, or a status change on a tracked Instrument.
- **Output** — a `DerivedDocument` (the first writer of that label): a summary of the change, the affected Instruments and GovernanceLinks, the parties affected (labelled as the agent's reading), and, on request, a draft comment.
- **Into the matter** — a draft is filed as a `draft` artifact on the requesting user's matter, with a matter task whose due date is the source-published close date.
- **Limits** — one draft per human request, no bulk generation (mass comment campaigns are a known abuse of rulemaking); every draft is labelled as AI-assisted and carries the not-legal-advice disclaimer; nothing is submitted by the platform, and submission is always the person's own act.

## Git as the record

Decided in [ADR 0009](adr/0009-git-record-store.md); summarised here.

- Records are files, one JSON document per entity, in a **separate data repository**, never in this one.
- Each ingestion run commits to a run branch. Commit trailers record `Produced-By`, `Reviewed-By`, `Source-URL`, `Content-Hash`, `Cycle-Id` and `Schema-Version`, so `git log`, `git diff` and `git blame` give the legal history and name the agent and source behind every field.
- Merging into the main branch is the human acceptance. No forge is required: branches and merges work locally (constitution §1), and a GitHub mirror is optional.
- The graph is a projection of the main branch, rebuilt idempotently by one projector that never deletes (`archived_at`).
- Tags (`law/<YYYY-MM-DD>`) mark the state of the law on a date, so an analysis records the tag it ran against and can be reproduced.
- Schema changes go through the same flow, with every record validated against the new generated schema before merge.
- The `AuditEvent` log remains the record of what agents did (constitution §4); git is the record of what the law was.

## Future: tamper-evident records

A later phase, after the git record is stable. Goal: make the record of the law, and of what the agents did with it, verifiable by parties who do not trust the operator.

- **Adopt before building a chain.** Signed commits (one key per agent), RFC 3161 trusted timestamps and OpenTimestamps already prove that a record existed unaltered at a date. A public or consortium chain is considered only if those fail the test below.
- **Anchoring, not storage.** If a chain is used, it holds tagged commit hashes only. Legal text and personal data never go on it.
- **Governance of the governors.** Changes to the schema, the agent roles and the reviewer policy are signed by maintainers, mirroring the GovernanceLink model applied to the platform itself.
- **The test.** A proof, admissible in court, that a given record was what the platform held at a given time.
- **Scope guard.** No tokens with monetary value, no on-chain execution of legal logic.

## Review question (constitution §13)

*Who is the stronger here, and what does this design do for them?* The parties that publish the most structured, machine-readable official material: federal agencies with the Federal Register's API over a state Attorney General's HTML press releases, and well-resourced organisations that appear in enforcement records as named, represented parties. A schema that captures only what is easy to parse would make their law look like the law. The design answers with mandatory attribution (no instrument without its issuing authority, jurisdiction and dates), a source tier that is labelled and never used to filter, a `confidence` that measures the producer and never legal weight, staleness that is shown rather than hidden, and individuals never named. The feedback pipeline drafts for the person who asks; it never mass-produces comments for whoever can afford to run it at scale.

## Implementation sequence

Spec numbers are assigned when each spec is written; the backlog ids hold the place until then.

| Order | Package | Scope | Backlog |
|---|---|---|---|
| 1 | [058-core-schema-contract](../specs/058-core-schema-contract/spec.md) | Pydantic models, record envelope, generated JSON Schema, Neo4j migration, quarantine kinds, `RecordStore` with its quarantine-and-graph implementation | — (direct request) |
| 2 | federal-register-adapter | One agency via the Federal Register API; first writer of `:Regulation`; Instrument, Action and CommentPeriod from one source | BL-20261114-01 |
| 3 | colorado-ag-adapter | coag.gov and the Colorado Register; deterministic HTML parsers; every item to human review | BL-20261114-02 |
| 4 | governance-review-loop | The LangGraph loop, the structuring and reviewer agents, the retry cap, the milestone report — and the first milestone run | BL-20261114-03 |
| 5 | git-record-store | [ADR 0009](adr/0009-git-record-store.md): the data repository, run branches, the projector, tags, seeded from the first run's accepted records | BL-20261114-04 |
| 6 | snapshots-and-reconciliation | Hash detection, status history, bounded propagation, source conflicts to a human | BL-20261114-05 |
| 7 | rulemaking-feedback | The analysis agent, `DerivedDocument`, matter drafts and tasks | BL-20261114-06 |
| — | later | Relabel existing nodes; tamper-evidence ADR; seed token; feature-catalog ids | BL-20261114-07 … 10 |

Steps 2 and 3 run in parallel once 058 lands. Every package passes `make lint`, `make typecheck`, `make test` and `make lint-specs`, and mirrors its follow-ups into [BACKLOG.md](../BACKLOG.md).

## Backlog

- **Seed token** (BL-20261114-09) — a compact, signed token encoding a record's provenance (source hash, snapshot, agent keys, anchoring reference). Verification is deterministic cryptography; a small local model may *explain* a verification result to a reader, never decide it. Depends on the tamper-evidence phase.

## Open questions

- Which federal agency — settled when the federal-register-adapter spec is clarified.
- Source snapshots that name individuals — whether to keep the verbatim text (hash-verifiable, never projected or retrieved as structured data) or redact it before storage (breaks hash verification against the source). Spec 058 OQ-1.
