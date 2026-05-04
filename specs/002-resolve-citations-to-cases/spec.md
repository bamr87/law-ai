# Spec: Resolve Citations to Case Nodes (Graph Densification)

- **ID**: 002-resolve-citations-to-cases
- **Status**: planned
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: BL-20260429-05 (graph densification)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1–11.

## 1. Problem & Motivation

Spec 001 ships citations as `(:Citation {normalized})` nodes connected to a single source `(:Case)` via `HAS_CITATION`. The cited case itself is rarely linked, so the graph is a star, not a network — defeating the GraphRAG advantage over plain vector search. We need to resolve `Citation.normalized` strings to existing `Case` nodes whenever possible and create `(:Case)-[:CITES]->(:Case)` edges.

Mirrors backlog item **BL-20260429-05** (`feature, high`).

## 2. Goals

- G1: Given a freshly extracted `ExtractionResult`, populate `Citation.target_case_id` for every citation that matches an existing `Case` alias.
- G2: Densify the graph by reusing the existing `MERGE_CITES_CYPHER` (no schema change beyond a new `Case.aliases: list[str]` property).
- G3: Make the resolver pure-async, idempotent, and safe to run on backfills.

## 3. Non-Goals

- NG1: Fuzzy matching across reporters (e.g. parallel cites). Phase 2.
- NG2: Cross-jurisdiction harmonization. Phase 2.
- NG3: New API endpoints — this is an internal ingestion enhancement.

## 4. User Stories

- As a **Precedent Hunter agent**, I want incoming opinions to be auto-linked to the cases they cite so that Cypher traversals (`(:Case)-[:CITES*1..3]->(:Case)`) return real precedent chains instead of empty results.
- As a **researcher**, I want the graph viewer to show citation networks the day after ingestion, not after a separate manual densification pass.

## 5. Functional Requirements

- **FR-1**: Add `Case.aliases: list[str]` populated from `ExtractionResult.aliases` (new optional field). Backward compatible — existing nodes without aliases are unaffected.
- **FR-2**: Add `app.db.citation_resolver.resolve_citations(session, normalized: list[str]) -> dict[str, str | None]` returning a `{normalized: case_id_or_None}` map.
- **FR-3**: Add `app.db.citation_resolver.densify_extraction(session, result: ExtractionResult) -> ExtractionResult` that mutates `result.citations[*].target_case_id` in place using FR-2.
- **FR-4**: `IngestionScout.run_and_commit` calls `densify_extraction` after `extract` and before `commit_extraction` (FR-3 reuse).

## 6. Non-Functional Requirements

- **NFR-IDEMPOTENT-1**: Re-running densification on the same `ExtractionResult` produces the same `target_case_id` values and creates zero new edges in Neo4j.
- **NFR-PERF-1**: Resolver issues exactly **one** Cypher round-trip per `ExtractionResult`, regardless of citation count (uses `UNWIND $normalized AS n`).
- **NFR-AUDIT-1**: Every resolved citation is logged via `app.core.provenance` with fields `{normalized, target_case_id, confidence, agent_version}`.
- **NFR-HITL-1**: No HITL change — densification only touches edges between already-approved nodes.

## 7. Data Model Impact

- **New property**: `Case.aliases: list[str]` (defaults to `[]`).
- **No new node labels.**
- **Existing edge reused**: `(:Case)-[:CITES]->(:Case)` from spec 001's `MERGE_CITES_CYPHER`.

Provenance fields (`source`, `confidence`, `ingest_timestamp`) remain on the `:CITES` edge per constitution §4.

## 8. API Surface

No public route changes. Internal contract:

```python
async def resolve_citations(
    session: AsyncSession, normalized: list[str]
) -> dict[str, str | None]: ...

async def densify_extraction(
    session: AsyncSession, result: ExtractionResult
) -> ExtractionResult: ...
```

## 9. Agent / Crew Impact

- `IngestionScout` (existing) gains one extra step: `densify_extraction` between `extract` and `commit_extraction`. No new tools.
- `PrecedentHunter` (existing) automatically benefits — its Cypher traversals start returning real `:CITES` chains.

## 10. Acceptance Criteria

- **AC-1**: Given a `Case {id:"a", aliases:["410 us 113"]}` exists, when an `ExtractionResult` from case `b` cites `"410 us 113"`, then `resolve_citations` returns `{"410 us 113": "a"}` and `densify_extraction` sets `target_case_id="a"` on that citation.
- **AC-2**: Given the same input as AC-1 run twice in a row, when `commit_extraction` is called both times, then exactly **one** `(:Case {id:"b"})-[:CITES]->(:Case {id:"a"})` edge exists (idempotency).
- **AC-3**: Given an `ExtractionResult` with N citations where none match any `Case.aliases`, when `densify_extraction` runs, then every `target_case_id` stays `None`, exactly one Cypher query is issued, and zero `:CITES` edges are created.
- **AC-4**: `mypy app/db/citation_resolver.py --strict` is clean and the module has ≥85% line coverage.

## 11. LegalBench Impact

- Tasks affected: `precedent_retrieval`, `case_relevance`.
- Expected delta: ≥ 0 pp (densification can only help). Actual delta recorded in PR after a real ingestion run; not part of acceptance for this spec because the hermetic test suite doesn't load LegalBench.

## 12. Risks & Open Questions

- **R-1**: Aliases are author-supplied; bad aliases pollute the graph. Mitigation: `confidence` on `:CITES` edge inherits from the source `ExtractionResult.confidence`, so HITL gate still applies upstream.
- **R-2**: Backfill cost — re-densifying historical cases needs a one-shot script. Captured as a follow-up rather than blocking this spec.

## 13. Out of Scope / Follow-ups

- Fuzzy / parallel-cite matching.
- Backfill script for historical opinions.
- `aliases` extraction from opinion headers (currently caller-supplied).
