# law-ai Core Schema Spec

> The original November 2026 draft of the core schema spec, kept verbatim as a historical record — read core-schema.md for the reviewed, living version.

A single shared contract for both the legal-system data model and the agent orchestration harness. Every agent and every data record validates against this spec. Change it here first, then everywhere else.

## Design principles

- Model the legal system as it actually operates: jurisdictions, authorities, the instruments they produce, the actions they take, and the governance relationships between them.
- One schema, two consumers: legal records and agent roles use the same entity types.
- Every record is traceable: source URL, retrieval date, jurisdiction, and the agent that produced it.
- Start narrow: federal plus Colorado, two agencies, one loop end to end. Widen only after the loop reconciles cleanly.

## Entity types

### Jurisdiction

A territory and level of government whose law applies.

- `id` — stable slug, e.g. `us-federal`, `us-co`, `us-co-denver`
- `name`
- `level` — `federal` | `state` | `local` | `tribal` | `international`
- `parent_id` — the enclosing jurisdiction, if any
- `notes`

### Authority

A body that makes, interprets, or enforces law within a jurisdiction: legislature, court, or agency.

- `id`
- `name`
- `jurisdiction_id`
- `kind` — `legislature` | `court` | `agency` | `executive` | `independent-body`
- `branch` — `legislative` | `judicial` | `executive` | `hybrid`
- `parent_authority_id` — the body above it in its own hierarchy (e.g. district court → appellate court)
- `powers` — list of `rulemaking` | `adjudication` | `enforcement` | `guidance` | `licensing`
- `website`

### Instrument

A written source of law or quasi-law.

- `id`
- `title`
- `kind` — `constitution` | `statute` | `regulation` | `case` | `executive-order` | `guidance` | `policy`
- `authority_id` — who issued it
- `jurisdiction_id`
- `citation` — canonical citation string
- `effective_date`
- `status` — `proposed` | `in-force` | `amended` | `repealed` | `vacated`
- `supersedes` — list of instrument ids
- `implements` — list of instrument ids this one carries out (e.g. a regulation implementing a statute)
- `source_url`
- `text_ref` — pointer to stored full text

### Action

A discrete event in which an authority does something: a rulemaking step, enforcement action, ruling, or audit.

- `id`
- `authority_id`
- `kind` — `rulemaking` | `enforcement` | `ruling` | `guidance-issued` | `audit` | `investigation`
- `date`
- `instrument_ids` — the instruments this action relies on or produces
- `subject` — who or what it was directed at
- `outcome`
- `source_url`

### GovernanceLink

The oversight relationship between any two entities. This is where accountability, review, and AI-governance obligations live.

- `id`
- `from_id` — the overseeing entity
- `to_id` — the overseen entity
- `relation` — `reviews` | `funds` | `appoints` | `audits` | `appeals-to` | `delegates-to` | `reports-to`
- `basis_instrument_id` — the instrument that establishes the relationship
- `notes`

## Common fields on every record

- `source_url`
- `retrieved_at`
- `produced_by` — agent id
- `reviewed_by` — agent id, empty until review passes
- `confidence` — `0.0`–`1.0`
- `review_status` — `pending` | `accepted` | `rejected`

## Agent roles and the loop

Agents map onto the same model. Each role is scoped to one Authority at a time.

1. **Ingestion agent** — owns one Authority. Pulls recent Instruments and Actions from official sources. Emits raw records with `review_status: pending`.
2. **Structuring agent** — fits raw records to the schema, resolves ids, links `implements` and `supersedes`, fills GovernanceLinks it can prove from the text.
3. **Reviewer agent** — plays the appellate role. Verifies every `source_url` resolves, every citation parses, every link has a basis. Accepts or rejects with a reason.
4. **Reconciliation** — rejected records go back to the structuring agent with the reason attached. The loop runs until the batch is fully accepted or a retry cap is hit, at which point remaining records are flagged for human review.

## First milestone

- Jurisdictions: `us-federal`, `us-co`
- Authorities: Colorado Attorney General; one federal agency with active AI-governance activity
- One full ingestion → structuring → review → reconcile loop on the last 90 days of Actions
- Exit criteria: all records accepted, zero broken source URLs, schema unchanged for two consecutive runs

## Official sources

Every Authority carries a list of official sources it is read from. Nothing enters the system from a secondary source.

- `source_id`
- `authority_id`
- `name` — e.g. Federal Register, regulations.gov, PACER, CourtListener, Colorado Judicial Branch, Colorado Secretary of State
- `url`
- `kind` — `rulemaking-docket` | `court-docket` | `opinions` | `register` | `guidance-page`
- `poll_cadence` — `daily` | `weekly` | `on-event`
- `parser` — id of the parser module that reads it
- `last_polled_at`

## Versioning and reconciliation over time

Records are never overwritten. Each Instrument and Action keeps a history of snapshots, so the platform can show what the law was on any date.

- `snapshots[]` — `{retrieved_at, source_url, content_hash, text_ref}`
- `diff_from_previous` — summary of what changed
- `status_history[]` — `{status, effective_date, basis_action_id}` (e.g. proposed → final → in-force → vacated)

Reconciliation runs after every poll:

1. Detect: compare the new snapshot's hash with the last one.
2. Classify: a diff triggers a status re-evaluation (new final rule, amendment, repeal, vacatur, appeal decided).
3. Propagate: mark every downstream record that `implements`, `supersedes`, or is governed by the changed one as `review_status: pending`.
4. Re-review: the reviewer agent re-runs on the propagated set; conflicts between two official sources are flagged for human review with both snapshots attached.

## Feedback pipeline

New developments flow to an analysis agent that produces something a person can act on.

- Trigger: a new Action of kind `rulemaking` with an open comment period, a new ruling, or a status change on a tracked Instrument.
- Analysis agent output: a plain summary of the change, the affected Instruments and GovernanceLinks, the parties affected, and a draft comment or position paper.
- `CommentPeriod` entity: `action_id`, `opens`, `closes`, `docket_url`, `draft_ref`, `status` (`open` | `submitted` | `closed`).
- Deadlines become tracked events; nothing is submitted without human sign-off.

## Git as the platform's source control

Git is the system of record for the whole platform: schema, parsers, agent definitions, and the legal records themselves.

- Records live as files (JSON or YAML, one per entity) in a data repository. Each ingestion run is a commit; each reviewer acceptance is a merge. The commit log is the audit trail.
- A snapshot of an Instrument is a commit touching that file, so `git log` and `git diff` give the legal history for free and `git blame` names the agent and source behind every field.
- Branches map onto the loop: ingestion writes to a run branch, structuring and review happen as a pull request, reconciliation is the merge. Rejected records are review comments on the PR.
- Schema changes go through the same PR flow, with a validation Action that checks every record against the new schema before merge.
- Tags mark the state of the law at a date, so any analysis can be reproduced against the exact records it saw.
- Ties into \[\[git-with-the-program\]\]: the git history itself becomes the core memory agents read to detect drift, obsolescence and regression in both the code and the law.

## Future: blockchain-backed security and governance

A later phase, after the git-based loop is stable. The goal is to make the record of the law, and of what the agents did with it, verifiable by parties who do not trust the operator.

- **Anchoring, not storage.** Records stay in git. Each tagged commit's hash is written to a public or consortium chain, so anyone can prove a snapshot existed at a date and has not been altered. Legal text and personal data never go on-chain.
- **Provenance.** Each record's `produced_by`, `reviewed_by`, and source hash are signed by the agent's key. Keys are registered on-chain, giving a tamper-evident chain of custody from official source to analysis.
- **Governance of the governors.** Changes to the schema, the agent roles, and the reviewer policy go through a multi-signature or on-chain vote among maintainers, mirroring the GovernanceLink model applied to the platform itself.
- **Access and licensing.** Where instrument text is paywalled or restricted, access rights can be issued as revocable tokens rather than shared credentials.
- **Candidate stack.** Decide later between a public L2 for cheap anchoring and a permissioned chain (e.g. Hyperledger-style) for consortium governance; both must satisfy the same test: a court-admissible proof that a given record was what the platform held at a given time.
- **Scope guard.** No tokens with monetary value, no on-chain execution of legal logic. Blockchain here is a notary and a governance ledger, nothing more.

## Backlog / roadmap

- [ ] **Seed token.** A compact, signed token that encodes a record's provenance (source hash, snapshot, agent keys, anchoring reference). A small, cheap model interprets the token locally and cross-validates it against the blockchain ledger, so a record can be verified without the full platform or a large model. Depends on the blockchain anchoring phase.

## Open decisions

- Storage format for the canonical schema: JSON Schema vs. Pydantic models as the source of truth
- Where full instrument text lives (repo, object store, or external reference only)
- How to version the schema once records exist
