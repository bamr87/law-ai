# Tasks: Docker-Backed Integration Tests for `densify_extraction`

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from
> [spec.md](spec.md). CI's [scripts/spec_validator.py](../../scripts/spec_validator.py)
> enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.

---

## T-001 — Write the three integration tests

- **Refs**: FR-1, FR-2, FR-3, AC-1, AC-2, AC-3, AC-5, NFR-AUDIT-1, NFR-COVERAGE-1, NFR-IDEMPOTENT-1, NFR-ISOLATION-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/db/test_citation_resolver_integration.py` (new)
- **Steps**:
  1. Import `resolve_citations` and `densify_extraction` from `law_ai.core.neo4j.citation_resolver`.
  2. Add three `@pytest.mark.integration @pytest.mark.asyncio` tests using the spec-013 fixtures `neo4j_integration_driver` + `clean_neo4j_db`:
     - `test_resolve_citations_hits_real_neo4j_alias_match` — seed
       `(:Case {id: 'brown', aliases: ['347 U.S. 483']})`, call
       `resolve_citations(session, ["347 U.S. 483"])`, assert mapping
       contains `{"347 U.S. 483": "brown"}` (AC-1).
     - `test_densify_extraction_idempotent` — seed the same case, build an
       `ExtractionResult` with one citation, call `densify_extraction`
       twice in fresh sessions, assert both calls return the same non-None
       `target_case_id` (AC-2, NFR-IDEMPOTENT-1).
     - `test_resolve_citations_no_match_returns_none` — without seeding any
       matching alias, call `resolve_citations(session, ["999 U.S. 999"])`
       and assert the mapping value is `None` (AC-3).
- **Verify**:
  - `cd backend && pytest -m integration -v -k citation_resolver_integration` exits 0 with three green tests (AC-4).
  - `cd backend && pytest -q` (no `-m integration`) does **not** collect or run any of the new tests (AC-5).
  - `mypy law_ai --strict` clean (no production-code changes; tests are not strict-typed).

## T-002 — Wire into `make test-integration` and CI

- **Refs**: FR-4, AC-4, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `Makefile` (no change — `test-integration` already runs `pytest -m integration -v`)
  - `.github/workflows/integration-tests.yml` (no change — runs the same selector on the same paths)
- **Steps**:
  1. Confirm by inspection that the new file is picked up by both entry points (no path filter excludes `tests/db/`).
  2. Run `make test-integration` locally with Docker available; capture the green output in the PR description.
- **Verify**:
  - `make test-integration` exits 0 locally.
  - The "Integration Tests" workflow on GitHub Actions runs the new tests and is green on this PR.

## T-003 — Update BACKLOG.md to mark BL-20260429-10 done

- **Refs**: spec metadata; constitution §11
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - [BACKLOG.md](../../BACKLOG.md)
- **Steps**:
  1. Move `BL-20260429-10` from **Claimed** to **Done** with the resolution line: *"Shipped via specs/014-densify-extraction-integration-tests."*
  2. Run `python scripts/backlog_lint.py` — must exit 0.
- **Verify**:
  - `python scripts/backlog_lint.py` exits 0.
  - `python scripts/spec_validator.py` exits 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from [spec.md](spec.md) covered by passing tests.
- `make lint && make test` green.
- `make test-integration` green locally **and** in CI.
- LegalBench delta: 0 pp (no reasoning change; spec NFR-LegalBench).
- `BL-20260429-10` moved to **Done** in [BACKLOG.md](../../BACKLOG.md).
- **`## Follow-ups Discovered` section below populated**.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a
> `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py))
> checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py))
> checks the BACKLOG mirror.

- **BL-20260526-01** — *test-gap, low* — Add a mutation variant test seeding two cases with overlapping aliases to assert `head(collect(c.id))` determinism matches BL-20260429-12 (spec-002 follow-up). _Surfaced in:_ specs/014-densify-extraction-integration-tests.
- **BL-20260526-02** — *test-gap, low* — Add an integration test asserting `test_citation_resolver_integration` tests are NOT collected by `pytest -q` (no `-m integration`) in the CI environment, confirming AC-5 isolation contract. _Surfaced in:_ specs/014-densify-extraction-integration-tests.
<!-- original placeholder below -->
pre-existing items (BL-20260429-11, BL-20260429-21) that are intentionally out of scope. -->
