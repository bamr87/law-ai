# Plan: Docker-Backed Integration Tests for IngestionScout

> Companion to [spec.md](spec.md). Describes **how** we satisfy FR-1 through FR-6 and NFR-PERF-1 through NFR-CI-COST-1.

## 1. Architecture Overview

```mermaid
flowchart TB
  subgraph CI["GitHub Actions (integration-tests.yml)"]
    Checkout["Checkout code"]
    Compose["docker compose up -d\nneo4j postgres redis"]
    Wait["Wait for services\n(health checks)"]
    Test["pytest -m integration"]
    Down["docker compose down -v"]
  end

  subgraph Local["Local Dev (make test-integration)"]
    ComposeL["docker compose up -d\nneo4j postgres redis"]
    TestL["cd backend && pytest -m integration"]
  end

  subgraph Tests["backend/tests/ingestion/test_scout_integration.py"]
    T1["test_commit_high_confidence_creates_case_and_edges"]
    T2["test_idempotency_no_duplicate_nodes"]
    T3["test_low_confidence_routes_to_postgres_pending_review"]
  end

  subgraph Fixtures["backend/tests/conftest.py"]
    DS["docker_services()\nsession scope"]
    Neo["neo4j_integration_driver()"]
    PG["postgres_integration_pool()"]
    Clean["clean_neo4j_db()"]
  end

  Compose --> Wait --> Test
  Test --> Down
  ComposeL --> TestL

  T1 --> Neo
  T1 --> PG
  T2 --> Neo
  T3 --> Neo
  T3 --> PG
  Neo --> DS
  PG --> DS
  Neo --> Clean
```

This spec adds **zero runtime code changes** to `IngestionScout` or any ingestion module. It is pure test infrastructure and CI wiring.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Test | `backend/tests/ingestion/test_scout_integration.py` | **New** — 3 tests (FR-1) |
| Fixtures | `backend/tests/conftest.py` | **Edit** — add `docker_services` (session), `neo4j_integration_driver`, `postgres_integration_pool`, `clean_neo4j_db` fixtures (FR-2, FR-3) |
| CI | `.github/workflows/integration-tests.yml` | **New** — Docker-backed integration-test job (FR-5) |
| Makefile | `Makefile` | **Edit** — add `test-integration` target (FR-6) |
| Docker Compose | `docker-compose.yml` | **Edit** — add healthcheck stanzas for neo4j, postgres, redis (R-3 mitigation) |
| Pytest config | `backend/pyproject.toml` `[tool.pytest.ini_options]` | **Unchanged** — `integration` marker already defined |

## 3. Data & Schema Migrations

**None.** Integration tests exercise the existing schema (spec 001 `Case` + `Citation` + `CITES`; spec 004 `pending_review`).

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Fixture orchestration | Custom `conftest.py` + `subprocess.run("docker compose ...")` | `pytest-docker` plugin | Resolved OQ-1: simpler, zero new deps, matches existing Makefile/task patterns |
| CI service orchestration | `docker compose` in job steps | GitHub Actions `services:` | Matches local dev UX; reuses existing `docker-compose.yml`; simpler for health-check passthrough |
| Neo4j cleanup strategy | `@pytest.fixture(scope="function")` runs `MATCH (n) DETACH DELETE n` before each test | Unique `Case.id` per test | NFR-ISOLATION-1: full isolation, simpler assertions (`count(c) = 1`), no cross-test pollution |
| Postgres cleanup | Use Django test DB isolation (truncate after test) | Nuke entire DB | Postgres tests reuse the existing Django test mechanisms; smaller blast radius |
| CI path filtering | `.github/workflows/integration-tests.yml` `on.pull_request.paths: [backend/**, .github/workflows/integration-tests.yml, docker-compose.yml]` | Run on every PR | NFR-CI-COST-1: skips docs-only or frontend-only PRs |

No constitution deviations. The [docs/constitution.md](../../docs/constitution.md) § "Testing Standards" mandates "≥ 1 integration test (real Neo4j/Postgres via `docker compose`)" — this spec closes that gap.

## 5. Provenance & Audit Hook-up

- **AC-4 (NFR-AUDIT-1):** Each integration test asserts `audit.AuditEvent.objects.filter(agent_name="IngestionScout").count() >= 1` **or** inspects logs for `[provenance]` lines. The latter is simpler and decouples from the ORM (which is unit-tested already).
- Integration tests verify the **side effects** (`Case` nodes in Neo4j, `PendingReview` rows in Postgres) rather than log format. The unit tests in `test_scout.py` already lock in the provenance contract; integration tests close the loop by confirming the full stack writes to real databases.

## 6. HITL Gates

**None specific to this spec.** The integration tests verify that `IngestionScout` routes low-confidence extractions to the `PendingReview` table (via Celery → ORM) — the admin HITL workflow is exercised by spec 011's unit tests. End-to-end Playwright coverage (admin login → approve → Neo4j commit) is deferred to BL-20260503-17.

## 7. Test Strategy

### New Integration Tests (FR-1)

File: `backend/tests/ingestion/test_scout_integration.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_commit_high_confidence_creates_case_and_edges(
    neo4j_integration_driver, clean_neo4j_db
):
    """AC-3, AC-4: commit a fixture opinion with multiple citations;
    assert the Case node + at least one CITES edge exist in Neo4j."""
    # Fixture: opinion with known citations that resolve to a pre-seeded target
    # Step 1: pre-seed a target case in Neo4j
    # Step 2: run scout.run_and_commit with a payload that cites the target
    # Step 3: Cypher query for (source)-[:CITES]->(target), assert edges >= 1

@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotency_no_duplicate_nodes(neo4j_integration_driver, clean_neo4j_db):
    """AC-1, AC-3, NFR-IDEMPOTENT-1: commit the same opinion twice;
    assert exactly one Case node exists."""
    # Step 1: run scout.run_and_commit(payload)
    # Step 2: run scout.run_and_commit(payload) again
    # Step 3: MATCH (c:Case {id: '<fixture_id>'}) RETURN count(c) AS n
    # Assert: n == 1

@pytest.mark.integration
@pytest.mark.asyncio
async def test_low_confidence_routes_to_postgres_pending_review(
    neo4j_integration_driver, postgres_integration_pool, clean_neo4j_db
):
    """AC-5, NFR-HITL-1: commit a forced-low-confidence opinion;
    assert PendingReview row exists and Case node does NOT exist in Neo4j."""
    # Fixture: opinion with confidence forced below 0.7 (small text, no citations)
    # Step 1: run scout.run_and_commit(payload)
    # Step 2: query ingestionapp_pendingreview for id=<fixture_id>
    # Step 3: MATCH (c:Case {id: '<fixture_id>'}) RETURN count(c)
    # Assert: row exists in Postgres, count(c) == 0 in Neo4j
```

### Fixtures (FR-2, FR-3, NFR-ISOLATION-1)

Add to `backend/tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def docker_services():
    """Spin up neo4j + postgres + redis for integration tests."""
    # subprocess.run(["docker", "compose", "up", "-d", "neo4j", "postgres", "redis"], check=True)
    # Wait for health (poll bolt://localhost:7687, pg ready, redis ping)
    # Yield
    # subprocess.run(["docker", "compose", "down"], check=False)

@pytest_asyncio.fixture(scope="session")
async def neo4j_integration_driver(docker_services):
    """AsyncDriver connected to the Docker-compose Neo4j."""
    # neo4j.AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "lawgraph-dev"))
    # Yield driver
    # await driver.close()

@pytest_asyncio.fixture(scope="session")
async def postgres_integration_pool(docker_services):
    """asyncpg.Pool connected to the Docker-compose Postgres."""
    # asyncpg.create_pool("postgresql://lawgraph:lawgraph-dev@localhost:5432/lawgraph")
    # Yield pool
    # await pool.close()

@pytest_asyncio.fixture(scope="function")
async def clean_neo4j_db(neo4j_integration_driver):
    """Wipe Neo4j before each integration test."""
    # async with neo4j_integration_driver.session() as session:
    #     await session.run("MATCH (n) DETACH DELETE n")
    # yield
```

### GitHub Actions Workflow (FR-5, NFR-CI-COST-1, NFR-PERF-1)

File: `.github/workflows/integration-tests.yml`

```yaml
name: Integration Tests

on:
  push:
    branches: [main]
    paths:
      - backend/**
      - .github/workflows/integration-tests.yml
      - docker-compose.yml
  pull_request:
    paths:
      - backend/**
      - .github/workflows/integration-tests.yml
      - docker-compose.yml

jobs:
  integration:
    name: Integration Tests (Docker)
    runs-on: ubuntu-latest
    timeout-minutes: 15  # NFR-PERF-1: enforce 2-min target + buffer
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install backend deps
        run: cd backend && pip install -e ".[dev,test]"
      - name: Start services
        run: docker compose up -d neo4j postgres redis --wait
      - name: Run integration tests
        run: cd backend && pytest -m integration -v
      - name: Teardown
        if: always()
        run: docker compose down -v
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-results
          path: backend/test-results/
```

### Makefile Target (FR-6)

Add to `Makefile`:

```make
test-integration:
	docker compose up -d neo4j postgres redis --wait
	cd backend && pytest -m integration -v
	docker compose down
```

### Docker Compose Health Checks (R-3 mitigation)

Add to `docker-compose.yml`:

```yaml
neo4j:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "lawgraph-dev", "RETURN 1"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s

postgres:
  # ... existing config ...
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U lawgraph"]
    interval: 10s
    timeout: 5s
    retries: 5

redis:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5
```

## 8. Fixture Opinions

Three fixture opinions will be defined in `test_scout_integration.py`:

1. **HIGH_CONF_FIXTURE** — ≥500 words, 3+ citations (at least one resolves to a pre-seeded target), court + judges present. Expected: `confidence ≥ 0.7`, commits to Neo4j, creates `CITES` edges.
2. **IDEMPOTENT_FIXTURE** — Same as HIGH_CONF but with a different case_id. Used twice in `test_idempotency_no_duplicate_nodes`.
3. **LOW_CONF_FIXTURE** — Empty `plain_text`, no citations, generic case_name. Expected: `confidence < 0.7`, routes to `PendingReview`, **not** in Neo4j.

The pre-seeded target case for HIGH_CONF_FIXTURE will be inserted in the test setup via a raw Cypher `CREATE` statement (e.g., `CREATE (:Case {id: 'target-123', title: 'Brown v. Board', ...})`).

## 9. Coverage Target (NFR-COVERAGE-1)

- **Current backend coverage:** 84.08% (126 tests, per spec 011).
- **Target:** ≥86% (+2 pp) after this spec.
- **Expected contribution:** The 3 new integration tests exercise `IngestionScout.run_and_commit` → `commit_extraction` → `densify_extraction` end-to-end, covering Cypher execution paths that unit tests mock. This should lift coverage on `backend/lawgraph/core/neo4j/{queries.py, citation_resolver.py}` and `backend/lawgraph/ingestionapp/services/scout.py` by ~2–3 pp collectively.
- **Gate:** `cd backend && pytest --cov=lawgraph --cov-fail-under=86` must pass before merging.

## 10. Rollout

- **Branch:** `feat/013-integration-tests` (created from `main`).
- **PR sequence:**
  1. **T-001** — Docker Compose health checks (R-3).
  2. **T-002** — Fixtures in `conftest.py` (FR-2, FR-3).
  3. **T-003** — Three integration tests (FR-1).
  4. **T-004** — Makefile target (FR-6).
  5. **T-005** — GitHub Actions workflow (FR-5).
- **Merge gate:** All five tasks pass `pytest -m integration` locally and green CI on the PR. Spec validator + backlog lint pass.
- **Post-merge:** Mark BL-20260429-01 as `Done` in [BACKLOG.md](../../BACKLOG.md); append any follow-ups discovered.

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| R-1: Docker-in-Docker on GitHub Actions is flaky | med | med | Use `docker compose --wait` with explicit health checks; retry on transient failures |
| R-2: Neo4j slow startup (30–60s) exceeds NFR-PERF-1 | low | med | Health check `start_period: 30s` absorbs the delay; tests themselves run in <30s |
| R-3: Missing health checks cause test flakiness | high | low | Addressed in T-001 — add health checks to neo4j/postgres/redis before writing tests |
| R-4: Integration tests interfere with unit tests | low | high | `@pytest.mark.integration` + `FR-4` (default pytest excludes integration) ensures isolation |
| R-5: Coverage target (86%) is missed | low | med | Dry-run coverage locally during T-003; if <86%, expand test assertions or add a 4th test |
| R-6: CI timeout (15 min) is exceeded | low | low | NFR-PERF-1 budgets 2 min; 15 min is 7× buffer. If timeout fires, inspect service logs |

## 12. Estimated Effort

| Task | Story Points (agent-hours) |
|------|----------------------------|
| T-001 — Docker Compose health checks | 1 |
| T-002 — Fixtures (docker_services, drivers, pools) | 2 |
| T-003 — Three integration tests + fixtures | 3 |
| T-004 — Makefile target | 0.5 |
| T-005 — GitHub Actions workflow | 1.5 |
| **Total** | **8 agent-hours** |

Assuming typical agent velocity (4–6 hours/day), this spec can land in 1.5–2 calendar days.

## 13. Success Criteria

- [ ] `pytest -m integration` passes locally with `make dev` stack running (AC-1).
- [ ] New GitHub Actions workflow runs on every PR touching `backend/**` (AC-2).
- [ ] `test_idempotency_no_duplicate_nodes` asserts `count(c) = 1` (AC-3).
- [ ] `test_commit_high_confidence_creates_case_and_edges` asserts `edges >= 1` (AC-4).
- [ ] `test_low_confidence_routes_to_postgres_pending_review` confirms row in Postgres + zero nodes in Neo4j (AC-5).
- [ ] Backend coverage ≥ 86% (AC-6, NFR-COVERAGE-1).
- [ ] CI runtime ≤ 2 minutes for integration-test job (NFR-PERF-1).
- [ ] Spec validator + backlog lint pass.
- [ ] No unresolved `OPEN QUESTION` markers in `spec.md`.


## 8. Rollout

- Local docker compose: works after `make dev`.
- Feature flag (if any) and default.
- Backfill / re-ingest needed? If yes, script path.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| … | low/med/high | low/med/high | … |

## 10. Estimated Effort

Story points / agent-hours; flag any task that needs human pairing.
