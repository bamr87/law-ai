# Spec: Docker-Backed Integration Tests for IngestionScout

- **ID**: 013-ingestion-integration-tests
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-05-07
- **Roadmap Epic**: Quality Gates — close test-gap identified in spec 001
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

The `IngestionScout` landed in spec 001 with unit tests (91% coverage), but **no Docker-backed integration tests**. Unit tests mock Neo4j sessions (via `FakeAsyncSession`) and the Celery/Postgres quarantine path (via `monkeypatch`). While those tests confirm the extraction logic and routing behavior, they do **not** verify:

- Neo4j `MERGE` idempotency (`NFR-IDEMPOTENT-1` from spec 001) — that re-running ingestion of the same opinion doesn't duplicate nodes or edges.
- Citation densification (`densify_extraction`) — that `CITES` edges are actually created when target cases exist in the graph.
- End-to-end smoke for `run_and_commit` against real Neo4j + Postgres + Celery (backed by Redis).

[BACKLOG.md](../../BACKLOG.md) item **BL-20260429-01** explicitly calls for this coverage: *"Add docker-backed integration tests for `IngestionScout.run_and_commit` covering AC-3 and NFR-IDEMPOTENT-1 (currently marked `@pytest.mark.integration` but no green run recorded)."* The current CI (`.github/workflows/ci.yml`) runs only unit tests; there are no integration-test jobs. This spec closes that gap.

## 2. Goals

- **G1:** Add a pytest integration-test suite (`backend/tests/ingestion/test_scout_integration.py`) marked `@pytest.mark.integration` that runs `IngestionScout.run_and_commit` against a real Neo4j + Postgres + Redis stack.
- **G2:** Verify NFR-IDEMPOTENT-1 from spec 001: re-running ingestion of the same opinion produces no duplicate `Case` nodes or `CITES` edges.
- **G3:** Verify AC-3 from spec 001: commit a known fixture opinion and assert both the `Case` node and at least one `CITES` edge exist in Neo4j.
- **G4:** Wire a GitHub Actions CI job that spins up the stack via Docker Compose, runs the integration suite, and tears down cleanly. This job should be required for PRs.

## 3. Non-Goals

- **NG1:** Load or performance tests — this spec adds correctness checks only.
- **NG2:** Playwright end-to-end tests involving the frontend or Django admin — those are follow-ups (e.g., BL-20260503-17).
- **NG3:** Full ingestion backfill from CourtListener — the integration tests use a small fixture set (≤ 5 opinions).
- **NG4:** Blackstone NER integration — spec 001 deferred that to BL-20260429-03; this spec tests the current `_extract_entities` implementation only.

## 4. User Stories

- As a **LawGraph maintainer**, I want every PR to run integration tests against Neo4j and Postgres, so that regressions in ingestion or citation linking are caught before merging.
- As a **developer**, I want to run `pytest -m integration` locally and have it spin up containers automatically (via pytest-docker or a fixture script), so that I can verify my changes without manually managing services.
- As a **CI engineer**, I want the integration-test job to run only when backend files change (not on docs-only PRs), so that CI minutes are not wasted.

## 5. Functional Requirements

- **FR-1:** A new test file `backend/tests/ingestion/test_scout_integration.py` containing at least three tests, each marked `@pytest.mark.integration`:
  - `test_commit_high_confidence_creates_case_and_edges`: commits a fixture opinion with multiple citations; asserts the `Case` node and at least one `CITES` edge exist via Cypher query.
  - `test_idempotency_no_duplicate_nodes`: commits the same opinion twice in sequence; queries Neo4j and asserts exactly one `Case` node with that `id` exists.
  - `test_low_confidence_routes_to_postgres_pending_review`: commits a fixture opinion with forced confidence < 0.7; asserts the `PendingReview` row exists in Postgres and the case is **not** in Neo4j.
- **FR-2:** A pytest fixture `neo4j_integration_driver` in `backend/tests/conftest.py` that yields a real `neo4j.AsyncDriver` connected to the Docker-compose stack. This fixture depends on a `docker_services` fixture (provided by `pytest-docker` or a custom subprocess wrapper).
- **FR-3:** A pytest fixture `postgres_integration_pool` in `backend/tests/conftest.py` that yields a real `asyncpg.Pool` connected to the Postgres service in the stack.
- **FR-4:** The integration tests run only when explicitly invoked via `pytest -m integration` or by the new CI job. The default `pytest` (unit tests) must not require Docker.
- **FR-5:** A GitHub Actions workflow file `.github/workflows/integration-tests.yml` that:
  - Triggers on `push` to `main` and `pull_request` paths matching `backend/**`, `.github/workflows/integration-tests.yml`, `docker-compose.yml`.
  - Spins up the stack via `docker compose up -d neo4j postgres redis`.
  - Waits for services to be ready (health checks or `dockerize -wait`).
  - Runs `cd backend && pytest -m integration`.
  - Tears down via `docker compose down -v`.
  - Uploads test results as artifacts (optional but recommended).
- **FR-6:** A Make target `make test-integration` that mirrors the CI steps for local runs.

## 6. Non-Functional Requirements

- **NFR-PERF-1:** The integration-test suite completes in ≤ 2 minutes on GitHub Actions runners (neo4j + postgres + redis spin-up time included).
- **NFR-ISOLATION-1:** Each integration test starts with a clean Neo4j database (either via a `@pytest.fixture(scope="function")` that runs `MATCH (n) DETACH DELETE n` before yielding the driver, or by using a unique `:Case {id}` per test to avoid collisions).
- **NFR-COVERAGE-1:** The integration tests must increase overall backend coverage by at least 2 pp (target ≥86%, currently at 84.08% per spec 011).
- **NFR-AUDIT-1:** Every integration test must verify that `provenance.log_agent_call` and `provenance.log_graph_query` were invoked (either by inspecting logs or by asserting the `AuditEvent` table has matching rows).
- **NFR-CI-COST-1:** The integration-test job should skip on docs-only or frontend-only PRs by using `paths` filters in `.github/workflows/integration-tests.yml`.

## 7. Data Model Impact

No schema changes. The integration tests exercise the existing `Case` + `Citation` + `CITES` + `PendingReview` shapes defined in spec 001 and spec 004.

## 8. API Surface

No new HTTP routes. Integration tests call `IngestionScout.run_and_commit` directly (Python module-level testing).

## 9. Agent / Crew Impact

- **IngestionScout**: integration tests verify its end-to-end contract against real datastores. No code changes to the agent itself are required (unless bugs are discovered during test authoring).
- No impact on `LegalAnalyst`, `PrecedentHunter`, or other crews.

## 10. Acceptance Criteria

- **AC-1:** Running `pytest -m integration` locally (with `make dev` stack already up) passes all three tests in `test_scout_integration.py` with zero failures.
- **AC-2:** The new GitHub Actions workflow `integration-tests.yml` runs on every push to `main` that touches `backend/**`, and the job is marked **required** in branch protection rules.
- **AC-3:** `test_idempotency_no_duplicate_nodes` commits the same fixture opinion twice and asserts:
  ```cypher
  MATCH (c:Case {id: '<fixture_id>'})
  RETURN count(c) AS n
  ```
  returns `n = 1`.
- **AC-4:** `test_commit_high_confidence_creates_case_and_edges` asserts at least one `CITES` edge exists via:
  ```cypher
  MATCH (c:Case {id: '<fixture_id>'})-[:CITES]->(target:Case)
  RETURN count(target) AS edges
  ```
  and `edges >= 1`.
- **AC-5:** `test_low_confidence_routes_to_postgres_pending_review` queries the `pending_review` table and asserts exactly one row with `id = '<fixture_id>'` and `confidence < 0.7`.
- **AC-6:** Backend coverage after this spec lands is ≥ 86% (target from NFR-COVERAGE-1).

## 11. LegalBench Impact

- Tasks affected: none directly (this spec adds test infrastructure, not reasoning logic).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1:** Docker-in-Docker on GitHub Actions can be flaky (networking, volume mounts). Mitigation: use `services:` instead of `docker compose` in the workflow if simpler.
- **R-2:** Neo4j Community Edition in CI may have slower startup times (30–60 s). Mitigation: add explicit health checks (`docker compose -f docker-compose.yml up --wait neo4j postgres redis`) to avoid test flakiness.
- **R-3:** Existing `docker-compose.yml` may need health-check stanzas for neo4j/postgres/redis if they are missing. Mitigation: add them in the plan phase (or as T-001 of this spec).

**Resolved OQ-1:** Use custom `conftest.py` fixtures that shell out to `docker compose`. Rationale: (1) [docs/constitution.md](../../docs/constitution.md) § "Testing Standards" mandates "≥ 1 integration test (real Neo4j/Postgres via `docker compose`)"; (2) the existing Makefile (`local-ai-up`, `local-ai-down`) and VS Code tasks already use `docker compose` directly; (3) no `pytest-docker` in `backend/pyproject.toml`; (4) simpler, zero new deps. Fixtures will invoke `docker compose up -d neo4j postgres redis` before the session and `docker compose down` after, mirroring the Makefile pattern.

**Resolved OQ-2:** Defer `densify_extraction` coverage to a separate spec. Rationale: (1) BL-20260429-10 is a distinct backlog item; (2) this spec's scope is `IngestionScout.run_and_commit` end-to-end correctness (idempotency + basic `CITES` edge creation); (3) citation resolution is a separate concern already tested at unit level in spec 002; (4) combining both would bloat the spec and delay the core integration-test infrastructure needed for all future ingestion work.

## 13. Out of Scope / Follow-ups

- **BL-20260429-10** — Docker-backed integration test for `densify_extraction` (citation resolution) against a real Neo4j. That will be a separate spec (or folded into a future spec that extends citation handling).
- **BL-20260503-17** — Playwright end-to-end test exercising the Django admin HITL flow. That's a higher-level test; this spec is module-level.
- **BL-20260429-06** — Smoke test for `scripts/ingest_sample.py --dry-run --limit 3` against mocked CourtListener. Orthogonal to the Docker-backed stack tests in this spec.
- Load/soak tests — not in scope for this spec.
