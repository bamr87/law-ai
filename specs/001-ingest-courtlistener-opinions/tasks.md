# Tasks: Ingest CourtListener Opinions

> Every requirement in [spec.md](spec.md) — `FR-1..6`, `NFR-PERF-1`, `NFR-SEC-1`, `NFR-AUDIT-1`, `NFR-HITL-1`, `NFR-IDEMPOTENT-1`, `AC-1..5` — must be referenced by at least one task. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) enforces this.

---

## T-001 — Add `ExtractionResult` Pydantic models

- **Refs**: FR-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/models/extraction.py` (new)
  - `backend/tests/models/test_extraction.py` (new)
- **Steps**:
  1. Define `Citation`, `Entity`, `ExtractionResult` Pydantic v2 models with `confidence: float = Field(ge=0, le=1)`.
  2. Re-export from `backend/app/models/__init__.py`.
- **Verify**:
  - `cd backend && pytest tests/models/test_extraction.py -q` passes.
  - `mypy app/models --strict` clean.

## T-002 — Implement `CourtListenerClient` with `httpx` + `tenacity`

- **Refs**: FR-1, NFR-SEC-1, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/ingestion/__init__.py` (new)
  - `backend/app/ingestion/courtlistener.py` (new)
  - `backend/tests/ingestion/test_courtlistener.py` (new)
  - `.env.example` (add `COURTLISTENER_API_TOKEN=`)
- **Steps**:
  1. Async client wrapping `https://www.courtlistener.com/api/rest/v4/opinions/` with `httpx.AsyncClient`, 30 s timeout, `tenacity` retry (max 3, exponential).
  2. Read `COURTLISTENER_API_TOKEN` from settings; attach as `Authorization: Token …` if present.
  3. Log every fetch via `core.provenance` with `source="courtlistener"`, `source_url`.
- **Verify**:
  - `pytest tests/ingestion/test_courtlistener.py -q` passes (uses `respx` mock).
  - Test asserts retry on 503 and bail-out on 4xx (other than 429).

## T-003 — Implement `IngestionScout` agent + Neo4j commit path

- **Refs**: FR-2, FR-3, FR-6, NFR-AUDIT-1, NFR-HITL-1, NFR-IDEMPOTENT-1, AC-3, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/db/__init__.py` (new)
  - `backend/app/db/neo4j.py` (new — async driver singleton)
  - `backend/app/db/queries.py` (new — `MERGE`-based Cypher)
  - `backend/app/db/neo4j_migrations/001_case_constraints.cypher` (new)
  - `backend/app/db/postgres_migrations/001_pending_review.sql` (new)
  - `backend/app/ingestion/scout.py` (new — `IngestionScout` class)
  - `backend/app/agents/registry.py` (register `IngestionScout`)
  - `backend/tests/ingestion/test_scout.py` (new — unit + integration)
- **Steps**:
  1. `extract(payload)` runs Eyecite + Blackstone, returns `ExtractionResult`.
  2. `run_and_commit(payload)` branches on `confidence`: `>= 0.7` → `MERGE` `Case` + `Citation` + `CITES`/`HAS_CITATION` edges; `< 0.7` → insert into `pending_review` (Postgres) or append to `backend/var/pending_review/<date>.jsonl` if Postgres is unreachable.
  3. Every Cypher `MERGE` sets `source`, `source_url`, `ingest_timestamp`, `agent_version`, `confidence`.
  4. Register agent in [registry.py](../../backend/app/agents/registry.py).
- **Verify**:
  - Unit: `pytest tests/ingestion/test_scout.py::test_extract_high_confidence -q` passes.
  - Unit: `pytest tests/ingestion/test_scout.py::test_low_confidence_routes_to_pending -q` (AC-5).
  - Integration (needs `docker compose up -d neo4j postgres`): `pytest -m integration tests/ingestion/test_scout.py::test_run_and_commit_creates_case_and_edge` (AC-3).
  - Integration: `pytest -m integration tests/ingestion/test_scout.py::test_idempotent_recommit` (NFR-IDEMPOTENT-1).

## T-004 — CLI entry point + Makefile target

- **Refs**: FR-4, FR-5, NFR-PERF-1, AC-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/scripts/ingest_sample.py` (new)
  - `Makefile` (add `ingest` target)
- **Steps**:
  1. `argparse` CLI with `--source courtlistener`, `--limit N` (default 500), `--dry-run`.
  2. Orchestrate fetch → extract → commit, print a run summary (`committed`, `pending`, `skipped`, `elapsed_s`).
  3. `make ingest` invokes `cd backend && python scripts/ingest_sample.py --limit 500 --source courtlistener`.
- **Verify**:
  - `make ingest --dry-run` prints summary against a `respx`-mocked client without network.
  - Manual: `make dev && make ingest` populates Neo4j with ≥ 450 cases inside 10 minutes (AC-1, NFR-PERF-1).
  - Manual: re-run `make ingest` and confirm `committed=0`, `skipped=500` (AC-2).

## T-005 — Surface `last_ingest_at` on `/api/health`

- **Refs**: AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/api/health.py`
  - `backend/app/db/queries.py` (add `get_last_ingest_at()`)
  - `backend/tests/api/test_health.py` (extend or create)
- **Steps**:
  1. Add Cypher `MATCH (c:Case) RETURN max(c.ingest_timestamp) AS last_ingest_at`.
  2. Include in health response; default `null` when no `Case` exists.
- **Verify**:
  - Unit: monkeypatch `get_last_ingest_at` and assert the field appears (defaults to `null`).
  - Integration: commit a fixture case, `GET /api/health` returns the matching ISO-8601 timestamp (AC-4).

## T-006 — Documentation refresh

- **Refs**: FR-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/data-model.md` (new)
  - `docs/data-sources.md` (new)
  - `docs/agent-roles.md` (flip `IngestionScout` row from "planned/stub" to "live")
- **Steps**:
  1. `docs/data-model.md`: document `Case`, `Citation`, `CITES`, `HAS_CITATION` shapes from spec §7; include the Cypher constraints from the migration.
  2. `docs/data-sources.md`: one table row per source; add CourtListener with API endpoint, license, rate limits.
  3. Update the `IngestionScout` row in `docs/agent-roles.md` to point at `backend/app/ingestion/scout.py`.
- **Verify**:
  - `python3 scripts/spec_validator.py specs/001-ingest-courtlistener-opinions` exits 0.
  - Links resolve (manual).

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-1..5` covered by passing tests; `AC-1` and `AC-2` confirmed manually with the run summary captured in the PR description.
- `make lint && make test` green; backend coverage on changed files ≥ 75 %.
- LegalBench: **not** run (no reasoning change; spec §11).
- Provenance manually verified by tailing logs during a live `make ingest`.
- `python3 scripts/spec_validator.py` exits 0.

---

## Follow-ups Discovered

> Mirrored into [BACKLOG.md](../../BACKLOG.md). Append, never delete.

- **BL-20260429-01** — *test-gap, med* — Docker-backed integration tests for `IngestionScout.run_and_commit` (AC-3, NFR-IDEMPOTENT-1).
- **BL-20260429-02** — *refactor, med* — Convert `_quarantine_postgres` to async (`asyncpg`) so HITL items reach Postgres in production.
- **BL-20260429-03** — *feature, low* — Reintroduce Blackstone NER for `_extract_entities` once lazy-loadable.
- **BL-20260429-05** — *feature, high* — Spec 002 candidate: resolve `Citation.normalized` strings to existing `Case` nodes; create `(:Case)-[:CITES]->(:Case)` edges.
- **BL-20260429-06** — *test-gap, low* — Smoke test for `scripts/ingest_sample.py --dry-run` against a `respx` cassette.
- **BL-20260429-07** — *doc-gap, low* — Add `docs/api.md` documenting the `/health` JSON contract.
