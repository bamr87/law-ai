# Spec: Docker-Backed Integration Tests for `densify_extraction`

- **ID**: 014-densify-extraction-integration-tests
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-05-08
- **Roadmap Epic**: Quality Gates — close test-gap identified in spec 002
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

`densify_extraction` (in `backend/law_ai/core/neo4j/citation_resolver.py`) is the function that maps extracted citation strings to real `Case` node IDs via `Case.aliases` in Neo4j. Every ingested opinion's `CITES` edges ultimately depend on it. Its unit tests (in `backend/tests/db/test_citation_resolver.py`) use a hand-rolled `FakeAsyncSession` that never touches a real database, meaning:

1. The Cypher query `RESOLVE_CITATIONS_CYPHER` is never executed against a live Neo4j. Schema drift or index changes could silently break citation resolution.
2. Idempotency of the mutation (`target_case_id` population) is not exercised end-to-end through an actual `AsyncSession`.
3. The `NFR-IDEMPOTENT-1` claim in spec 002 ("read-only resolver → idempotent by construction") is only asserted by inspection, not by test.

The unit test file itself documents this gap explicitly:

> "Uses a hand-rolled `FakeAsyncSession` so the tests stay hermetic — no
> Docker / Neo4j required (BL-20260429-10 will add the integration variant)."

This spec closes that gap.

## 2. Origin & Background

- **BL-20260429-10** — *test-gap, med* — Add Docker-backed integration test for
`densify_extraction` against a real Neo4j (currently only `FakeAsyncSession`). _Surfaced in:_ specs/002-resolve-citations-to-cases.

## 3. Goals

- G1: Prove `densify_extraction` correctly resolves citations against a live Neo4j `Case.aliases` list using a real `AsyncSession`.
- G2: Prove idempotency: running `densify_extraction` twice on the same input produces the same mapping (no duplicate mutations, no state corruption).
- G3: Prove the no-match path: when no `Case` alias matches the citation string, `target_case_id` remains `None` and no edge is created.
- G4: All new tests run only when Docker is available (`@pytest.mark.integration`) and reuse the fixture infrastructure added by spec 013.

## 4. Non-Goals

- NG1: Does not test `commit_extraction` or full `IngestionScout.run_and_commit` — those are covered by spec 013.
- NG2: Does not add the `scripts/densify_existing.py` backfill script (BL-20260429-11 is a separate item).
- NG3: Does not change the `RESOLVE_CITATIONS_CYPHER` logic.

## 5. User Stories

- As a **backend engineer**, I want the citation-resolution integration test to
catch Neo4j schema drift before it reaches production, so that `CITES` edges are not silently skipped on future releases.
- As a **QA reviewer**, I want an objective, runnable proof of idempotency for
`densify_extraction`, so that I can approve merges touching citation logic with confidence.

## 6. Functional Requirements

- **FR-1**: Create `backend/tests/db/test_citation_resolver_integration.py` with at least three `@pytest.mark.integration @pytest.mark.asyncio` tests:
  - `test_resolve_citations_hits_real_neo4j_alias_match` (G1, AC-1)
  - `test_densify_extraction_idempotent` (G2, AC-2, NFR-IDEMPOTENT-1)
  - `test_resolve_citations_no_match_returns_none` (G3, AC-3)
- **FR-2**: Tests use `neo4j_integration_driver` and `clean_neo4j_db` fixtures from `backend/tests/conftest.py` (added by spec 013). No new fixtures required.
- **FR-3**: Tests must not run as part of the default `pytest` suite; they are
gated behind `-m integration`. The existing `pyproject.toml` marker declaration covers this — no changes needed.
- **FR-4**: `make test-integration` (spec 013 Makefile target) must execute the new tests alongside the existing spec 013 suite without additional configuration.

## 7. Non-Functional Requirements

- **NFR-PERF-1**: New integration test file adds ≤ 30 seconds to `make test-integration` total run time (three lightweight Cypher transactions).
- **NFR-ISOLATION-1**: Each test starts with a clean Neo4j graph via the `clean_neo4j_db` fixture (`MATCH (n) DETACH DELETE n`).
- **NFR-IDEMPOTENT-1**: `test_densify_extraction_idempotent` MUST call
`densify_extraction` twice with the same `ExtractionResult` and assert the mapping is identical on both calls.
- **NFR-COVERAGE-1**: Backend coverage must not drop below 84% (current 84.03%).
The new tests exercise the live Cypher path in `citation_resolver.py`; net coverage effect is neutral-to-positive.
- **NFR-AUDIT-1**: `densify_extraction` already logs via `core.provenance`; no additional provenance wiring required.

## 8. Data Model Impact

None — no new nodes, edges, or schema changes. The tests CREATE/DETACH DELETE `Case` nodes within the `clean_neo4j_db` per-test lifecycle.

## 9. API Surface

None — no new routes.

## 10. Agent / Crew Impact

None — `densify_extraction` is a graph utility called by `IngestionScout`, not an agent itself.

## 11. Acceptance Criteria

- **AC-1**: `test_resolve_citations_hits_real_neo4j_alias_match` — Given a
`Case` node with `aliases: ["347 U.S. 483"]` pre-seeded in Neo4j, when `resolve_citations(session, ["347 U.S. 483"])` is called, then the returned mapping contains `{"347 U.S. 483": "<case_id>"}` with a non-None value.
- **AC-2**: `test_densify_extraction_idempotent` — Given the same pre-seeded
`Case` and the same `ExtractionResult` with one citation, when `densify_extraction` is called twice in separate `AsyncSession`s, then both calls return the same non-None `target_case_id`.
- **AC-3**: `test_resolve_citations_no_match_returns_none` — Given no `Case`
nodes match the citation string `"999 U.S. 999"`, when `resolve_citations(session, ["999 U.S. 999"])` is called, then the mapping value is `None`.
- **AC-4**: `pytest -m integration -v` exits 0 with all three new tests green.
- **AC-5**: `pytest -q` (unit suite, no `-m integration`) completes without collecting or running any of the new tests.

## 12. LegalBench Impact

- Tasks affected: none (citation resolver is infrastructure, not a reasoning component).
- Expected delta: 0 pp (no change to model logic).

## 13. Risks & Open Questions

- **R-1**: The `clean_neo4j_db` fixture uses `MATCH (n) DETACH DELETE n` — proven working by spec 013 infrastructure; low risk.
- **R-2**: `densify_extraction` requires an active `AsyncSession`; tests will open one via `neo4j_integration_driver.session()` async context manager.

_No open questions — spec 013 resolved the infrastructure questions (custom conftest fixtures, Docker availability) that would have applied here._

## 14. Out of Scope / Follow-ups

- **BL-20260429-11** — Backfill script `scripts/densify_existing.py`.
- **BL-20260429-21** — Docker-backed integration test for `graph_queries.neighborhood`.
