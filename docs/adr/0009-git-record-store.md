# ADR 0009 — Git as the record for the core-schema layer

- **Status**: proposed — decided by @bamr87 on 2026-11-13 (go; lands after the first loop run). Moves to `accepted` when the PR that carries it merges.
- **Date**: 2026-11-13
- **Spec**: design in [docs/core-schema.md](../core-schema.md); contract in [specs/058-core-schema-contract](../../specs/058-core-schema-contract/spec.md); implementation tracked as BL-20261114-04
- **Constitution clauses touched**: none amended. The decision operates inside §1 (local-first must remain reachable), §4 (provenance; never hard-delete), §5 (HITL) and §12 I1 (no auto-merge).
- **Supersedes / Superseded by**: none

## Context

Law AI's system of record today is Neo4j for the knowledge graph, Postgres for the `PendingReview` quarantine and the `AuditEvent` mirror, and an append-only JSONL log behind both ([data-model.md](../data-model.md)). Nodes are updated in place with `MERGE`; nothing keeps a node's earlier states.

The core-schema layer ([core-schema.md](../core-schema.md)) needs more than that. Records must never be overwritten. Each Instrument and Action keeps its snapshots and status history, so the platform can show what the law was on a date. An analysis must be reproducible against the exact records it saw. Every field must be attributable to the agent and source that produced it, and to the human who accepted it. Building that inside Neo4j means designing snapshot nodes, version chains, diffs and tags from scratch. Git already provides all of them — history, diff, blame, content addressing, signed commits and tags — and the later tamper-evidence phase anchors exactly what git produces: commit hashes.

## Decision

1. **Records are files in a separate data repository.** One JSON document per entity — Authority, Instrument, Action, GovernanceLink, OfficialSource, CommentPeriod — validated against the JSON Schema generated from the spec 058 Pydantic models. The repository's path is configured (`LAW_AI_DATA_REPO`); it is never this code repository, because AGENTS.md forbids committing generated artifacts and data churn would swamp code review.
2. **The graph is a projection.** One projector reads the data repository's main branch and `MERGE`s it into Neo4j, idempotently. A file that disappears sets `archived_at`; the projector never deletes (§4). Retrieval keeps reading Neo4j. The projector is the only writer of the core-schema labels, the way each scout is the only writer of its own labels (the intent of §12 I1).
3. **Branches carry the review loop.** Each ingestion cycle commits to its own run branch (`run/<cycle-id>`). Agent verdicts ride as commit trailers. Merging a run branch into main is the human acceptance — never an agent's or a workflow's (§5, §12 I1).
4. **Trailers make blame meaningful.** Every commit records `Produced-By`, `Reviewed-By`, `Source-URL`, `Content-Hash`, `Cycle-Id` and `Schema-Version`.
5. **Tags mark the law on a date.** `law/<YYYY-MM-DD>` tags the main branch; an analysis records the tag it ran against.
6. **Text is content-addressed.** Public-domain official text is stored under its `sha256`, deduplicated by hash. Sources with a restricted licence or hosting terms (the Municode posture in [data-sources.md](../data-sources.md)) keep an external reference only.
7. **Local-first, forge optional.** Branches, merges and tags are local git operations; the product needs no GitHub or other forge to run (§1). Mirroring the data repository to a forge, and reviewing run branches as pull requests there, is an operator's choice.
8. **Two logs, two jobs.** The `AuditEvent` log stays the record of what agents did — every model call, tool call and retrieval (§4). Git is the record of what the law was and who accepted it. Neither replaces the other.
9. **Scope.** The core-schema layer only. The existing corpora (CourtListener cases, CRS, the Denver code) stay in Neo4j as today; moving them is a separate decision with its own scale and licence questions.
10. **Sequencing.** This lands after the first loop run. Until then the loop writes through the `RecordStore` interface (spec 058) into the quarantine and graph. The git store is a second `RecordStore` implementation, and a one-time export of the first run's accepted records seeds the data repository.

## Consequences

- History, diff, blame and tags come with the store; the versioning design in core-schema.md needs no bespoke snapshot model.
- Any analysis can be re-run against the tag it recorded.
- The record becomes verifiable outside the platform: anyone with the repository can check a commit's hash, and the tamper-evidence phase can sign and timestamp those commits.
- Two stores must agree. Projection drift is possible, so the git-record-store spec ships a check that compares the main branch against the graph and reports differences instead of fixing them silently.
- Product code now writes to git. The spec that implements this picks the library (or the `git` binary in the backend image) with the licence and security note §8 requires. This is data written by the product into its own record, not the development harness the hub took over in 2026-10 ([spec-driven.md](../spec-driven.md)).
- Git slows down at millions of files. The core-schema layer is far below that; the existing case corpus, which is not, is out of scope (Decision 9).

## Alternatives Considered

1. **Version inside Neo4j** (snapshot nodes, version chains). Rejected: it rebuilds history, diff and tagging by hand, and the result is not verifiable outside the platform. LAWAI-016's as-of-date queries still sit on top of the projection.
2. **Postgres temporal tables or an event-sourced log.** Viable. Rejected because it gives no blame, no tags and no signed history for free, and the tamper-evidence phase would have to invent what git commits already are.
3. **Dolt** (git-style versioned SQL database, Apache-2.0). Rejected for now as a new stack component under §2; revisit if file count becomes a constraint.
4. **Records in this repository.** Rejected: AGENTS.md forbids committing generated artifacts, and every ingestion run would land in code review.
5. **GitHub pull requests as the review queue.** Rejected as a runtime dependency: §1 requires a fully local run. Kept as an optional mirror (Decision 7).
