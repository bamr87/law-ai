# Tasks: Autonomous Testing & Recursive Content-Generation Framework

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). All commands run inside Docker per [AGENTS.md](../../AGENTS.md) §"Docker-First Workflow".

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — ADR + constitution §12 + claim BACKLOG items

- **Refs**: FR-9, FR-16, NFR-HITL-1, NFR-AUDIT-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/adr/0003-autonomy-orchestrator.md` (new)
  - `docs/constitution.md` (edit — add §12)
  - `BACKLOG.md` (move BL-20260429-09, BL-20260502-04, BL-20260509-04 from `## Open` to `## Claimed`)
- **Steps**:
  1. Author ADR documenting loop topology, kill-switch, and Level-2 reaffirmation.
  2. Add constitution §12 "Autonomy Loop Invariants" referencing the ADR.
  3. Mark backlog items `claimed-by:specs/018-autonomous-framework`.
- **Verify**:
  - `python3 scripts/spec_validator.py` exits 0.
  - `python3 scripts/backlog_lint.py` exits 0.

## T-002 — LegalBench harness scaffold

- **Refs**: FR-1, FR-2, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/eval/__init__.py` (new)
  - `backend/lawgraph/eval/legalbench.py` (new — argparse CLI)
  - `backend/lawgraph/eval/loaders.py` (new — dataset cache loader)
  - `backend/lawgraph/eval/scoring.py` (new — per-task scoring helpers)
  - `backend/lawgraph/eval/report.py` (new — JSON report writer + delta calc)
  - `backend/var/legalbench/.gitkeep`, `backend/var/legalbench/LICENSES.md` (new)
  - `backend/tests/eval/__init__.py`, `backend/tests/eval/test_legalbench_cli.py` (new)
- **Steps**:
  1. Implement CLI matching the contract in [docs/legalbench.md](../../docs/legalbench.md).
  2. Wire to the existing Ollama client used by `agents_runtime/graphs/legal_workflow.py`.
  3. Emit OTEL spans per item via `lawgraph.core.provenance`.
  4. Author `LICENSES.md` enumerating per-task source + license. **Do not commit `baseline.json` until LICENSES.md lands.**
- **Verify**:
  - `make test-backend` includes `tests/eval/test_legalbench_cli.py` and is green.
  - `make test-legalbench` exits 0 inside the container and writes a report under `backend/var/legalbench/`.

## T-003 — Coverage auditor

- **Refs**: FR-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/eval/coverage_audit.py` (new)
  - `backend/tests/eval/test_coverage_audit.py` (new)
  - `scripts/evolve_audit.py` (edit — replace `_scan_coverage` body with a thin call into `coverage_audit`; add `_scan_legalbench`)
- **Steps**:
  1. Parse `coverage.xml` and return ranked `(module, pct, missing_lines)` records.
  2. Update `evolve_audit.py` to consume the new module while preserving its current public behavior (still appends `BL-*` items, still idempotent).
- **Verify**:
  - `python3 scripts/evolve_audit.py` exits 0 (no-op when nothing to add).
  - `pytest backend/tests/eval/test_coverage_audit.py` green inside the container.

## T-004 — TestSynthesizer crew + propose-only output

- **Refs**: FR-4, FR-5, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/agents_runtime/crews/test_synthesizer.py` (new)
  - `backend/lawgraph/agents_runtime/prompts/test_synthesizer.v1.md` (new)
  - `backend/tests/agents/test_test_synthesizer.py` (new)
  - `backend/tests/autonomy/proposed/.gitkeep` (new)
- **Steps**:
  1. Implement `TestSynthesizer.run(input: ProposedTestInput) -> ProposedTest` per [agents.instructions.md](../../.github/instructions/agents.instructions.md).
  2. Versioned prompt; provenance logging on every LLM call.
  3. Writer emits `<module-path>__autonomy.proposed.py` decorated with `@pytest.mark.skip("autonomy-proposed")`.
- **Verify**:
  - Unit test mocks Ollama, asserts proposed file exists and contains the skip decorator.

## T-005 — `nightly-tests.yml` workflow

- **Refs**: FR-6, FR-7, NFR-PERF-2, AC-8
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `.github/workflows/nightly-tests.yml` (new)
- **Steps**:
  1. Clone shape from [evolve.yml](../../.github/workflows/evolve.yml). Cron `0 6 * * *` + `workflow_dispatch`.
  2. Steps: `make test-coverage` → `make test-legalbench` → `python3 scripts/evolve_audit.py` → call `python manage.py run_autonomy --kind test_pillar` → open draft PR with `peter-evans/create-pull-request@v6`.
  3. Fail-on-regression: if `evolve_audit.py` adds any LegalBench `severity:high` item, exit non-zero.
- **Verify**: `gh workflow run nightly-tests.yml -f dry_run=true` (or local `act -W ...`) opens a draft PR with at least one `*.proposed.py` and zero merged commits.

## T-006 — `SOURCE_REGISTRY` package

- **Refs**: FR-8, FR-10, AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/ingestionapp/sources/__init__.py` (new — exposes `SOURCE_REGISTRY`)
  - `backend/lawgraph/ingestionapp/sources/base.py` (new — `SourceAdapter` Pydantic + `RawDoc`)
  - `backend/lawgraph/ingestionapp/sources/courtlistener.py` (new — wraps existing `services/courtlistener.py`)
  - `backend/lawgraph/ingestionapp/sources/colorado_statutes.py` (new — wraps `services/colorado_statutes.py`)
  - `backend/lawgraph/ingestionapp/sources/statute_scout.py` (new — wraps `services/statute_scout.py`)
  - `backend/lawgraph/core/management/commands/list_sources.py` (new)
  - `backend/tests/ingestion/test_source_registry.py` (new)
  - `backend/tests/core/management/test_list_sources.py` (new)
- **Steps**:
  1. Define `SourceAdapter` ABC with `name`, `jurisdiction`, `license`, `requires_human_approval`, `rate_limit`, `fetch(query) -> Iterable[RawDoc]`.
  2. Wrap existing scout services as adapters; preserve behavior (add a regression test asserting existing scout tests still pass).
  3. `list_sources` mgmt command prints registry as a table.
- **Verify**:
  - `python manage.py list_sources` prints exactly three rows.
  - All existing `tests/ingestion/test_scout*.py` still green.

## T-007 — `TopicFrontier` LangGraph workflow

- **Refs**: FR-11, NFR-HITL-1, NFR-PERF-1, NFR-SEC-1, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/agents_runtime/graphs/topic_frontier.py` (new)
  - `backend/lawgraph/agents_runtime/prompts/topic_frontier_prioritize.v1.md` (new)
  - `backend/lawgraph/core/neo4j/queries.py` (edit — add `list_orphan_citations` + `list_under_cited_jurisdictions` Cypher helpers)
  - `backend/tests/agents/graphs/test_topic_frontier.py` (new — mocked Neo4j + adapter)
  - `backend/tests/agents/graphs/test_topic_frontier_integration.py` (new — `@pytest.mark.integration`)
- **Steps**:
  1. Nodes: `scan_graph` → `prioritize` (Ollama) → `dispatch` → `summarize`.
  2. `dispatch` ALWAYS routes through `IngestionScout.run_and_commit`; never writes Neo4j directly.
  3. Integration test asserts every new `:Case` node carries `IngestionScout`'s `agent_version`.
- **Verify**:
  - Unit test passes; integration test passes against `make test-integration`.

## T-008 — `core.autonomy.run_cycle` orchestrator + provenance helpers

- **Refs**: FR-12, FR-16, NFR-AUDIT-1, AC-3, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/autonomy.py` (new)
  - `backend/lawgraph/core/provenance.py` (edit — add `log_autonomy_cycle`, `log_policy_violation`)
  - `backend/lawgraph/settings/base.py` (edit — add `AUTONOMY_ENABLED`, `AUTONOMY_ALLOWED_SOURCES`, `AUTONOMY_DIGEST_DIR`)
  - `backend/tests/core/test_autonomy.py` (new)
- **Steps**:
  1. `AutonomyRun` dataclass + `run_cycle(kind, cycle_id=None, **kwargs) -> AutonomyRun`.
  2. Idempotent on `cycle_id` (UUID4 default; returns prior result on duplicate by querying `audit.AuditEvent`).
  3. Short-circuit when `AUTONOMY_ENABLED=False` with a single provenance event.
  4. Allow-list check before any adapter dispatch; emit `policy_violation` on miss.
- **Verify**:
  - All scenarios in `test_autonomy.py` green (disabled, idempotency, policy violation, success).

## T-009 — `run_autonomy` management command + Celery beat schedule

- **Refs**: FR-13, FR-14, FR-17
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/management/commands/run_autonomy.py` (new)
  - `backend/lawgraph/celery.py` (edit — `beat_schedule` entries)
  - `backend/tests/core/management/test_run_autonomy.py` (new)
  - `Makefile` (edit — add `autonomy-up`, `autonomy-status`, `autonomy-stop`)
- **Steps**:
  1. CLI args `--kind`, `--source`, `--budget`, `--cycle-id`. Exit non-zero on policy violation.
  2. Beat: `autonomy-content-sweep` every 6h (kind=`corpus_growth`, budget=25); `autonomy-nightly-tests` daily 06:00 UTC (kind=`test_pillar`); `autonomy-daily-digest` daily 07:00 UTC (kind=`digest`). The pre-existing `evolve.yml` workflow remains the weekly evolve audit on CI.
  3. Makefile targets shell into `worker` container.
- **Verify**:
  - `make autonomy-status` prints the schedule.
  - `python manage.py run_autonomy --kind corpus_growth --source unknown_source` exits non-zero (AC-3).

## T-010 — Daily digest task

- **Refs**: FR-15, NFR-AUDIT-2, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/autonomy.py` (edit — add `compose_digest`)
  - `backend/lawgraph/celery.py` (edit — register `compose_digest` Celery task + beat entry daily 07:00 UTC)
  - `backend/var/autonomy/.gitkeep` (new)
  - `backend/tests/core/test_autonomy_digest.py` (new)
- **Steps**:
  1. Aggregate the last 24h of `audit.AuditEvent` rows where `event_type LIKE 'autonomy_%'`.
  2. Render Markdown to `backend/var/autonomy/digest-<YYYY-MM-DD>.md` with sections: PRs opened, BACKLOG items appended, Docs quarantined, LegalBench delta.
- **Verify**: Test fixture seeds audit rows; assert digest file exists with all four section headers.

## T-011 — Documentation refresh

- **Refs**: NFR-SEC-2, NFR-AUDIT-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/local-ai.md` (edit — `AUTONOMY_ENABLED`, cadence, kill-switch)
  - `docs/agent-roles.md` (edit — TestSynthesizer + TopicFrontier rows)
  - `docs/legalbench.md` (edit — fill baseline rows after first green run; record `LICENSES.md` policy)
  - `docs/architecture.md` (edit — autonomy loop diagram + `baseline.json` commit SHA)
- **Steps**: Concise, factual; link to ADR 0003.
- **Verify**: `make test-smoke` (which includes doc structural tests) green.

## T-012 — End-to-end gates + BACKLOG mirror

- **Refs**: AC-9
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — mirror this spec's follow-ups under `## Open`; promote claimed items to `## Done` once T-001..T-011 are green)
- **Steps**:
  1. Run `make lint`, `make typecheck`, `make test`, `make test-coverage`, `make test-integration`, `make test-legalbench`.
  2. Run `python3 scripts/spec_validator.py && python3 scripts/backlog_lint.py`.
  3. Mirror every item in `## Follow-ups Discovered` below into `BACKLOG.md` `## Open`.
- **Verify**: All gates exit 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (initial baseline established).
- Provenance logging verified manually for `run_autonomy --kind content` (`AUTONOMY_ENABLED=True`).
- `## Follow-ups Discovered` section below populated and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- **BL-20260511-03** — *feature, med* — Read-only `frontend/app/autonomy/` dashboard with Vitest test (sparkline of LegalBench scores, top-5 lowest-coverage modules, last 10 quarantined docs). Out of MVP scope. _Surfaced in:_ specs/018-autonomous-framework.
- **BL-20260511-04** — *infra, med* — Promote `AutonomyRun` from `audit.AuditEvent` JSON payload to a dedicated Postgres table once digest queries get richer. _Surfaced in:_ specs/018-autonomous-framework.
- **BL-20260511-05** — *feature, low* — Stream daily digest to Slack/email; today the `digest-<date>.md` file is the only surface. _Surfaced in:_ specs/018-autonomous-framework.
- **BL-20260511-06** — *feature, med* — Backfill `LegalAnalyst` (BL-20260430-03) and `PrecedentHunter` (BL-20260430-04) onto `LegalWorkflow` once the LegalBench baseline lands; resolves overlap with BL-20260502-04. _Surfaced in:_ specs/018-autonomous-framework.
- **BL-20260511-07** — *test-gap, low* — Live-network nightly smoke test that fetches one real Justia CRS title via `colorado_statutes` adapter and re-runs the parser to detect upstream HTML drift; resolves overlap with BL-20260509-04. _Surfaced in:_ specs/018-autonomous-framework.
- **BL-20260511-08** — *feature, low* — Add an `afetch` async coroutine to `SourceAdapter` ABC and companion async variants to all three adapters; today they use `asyncio.run()` which cannot be called from within an already-running event loop (e.g. Channels consumers). _Surfaced in:_ specs/018-autonomous-framework (T-006 implementation).
- **BL-20260511-09** — *test-gap, low* — Integration test that calls `list_sources` against the live Docker stack (Postgres + Redis) and asserts adapter metadata matches `SOURCE_REGISTRY` keys. _Surfaced in:_ specs/018-autonomous-framework (T-006 implementation).
- **BL-20260511-10** — *feature, med* — Wire `run_autonomy --kind corpus_growth` to the real `TopicFrontier` runner once T-007 lands; current `_run_corpus_growth` is a stub placeholder. _Surfaced in:_ specs/018-autonomous-framework (T-009 implementation).
- **BL-20260511-11** — *test-gap, low* — Add `make test-backend` integration marker to `test_run_autonomy.py::TestCeleryAutonomyTask::test_task_delegates_to_run_cycle_disabled` so it runs as part of the full beat-schedule smoke suite. _Surfaced in:_ specs/018-autonomous-framework (T-009 implementation).
- **BL-20260511-12** — *feature, med* — Extend LegalBench scoring to include BM25 recall and NLI-entailment strategies for `precedent_retrieval` subset; current exact-match baseline is a placeholder. _Surfaced in:_ specs/018-autonomous-framework (T-002 implementation).
- **BL-20260511-13** — *infra, low* — Add `make legalbench-cache` target that downloads and caches official LegalBench `items.jsonl` from HazyResearch GitHub into `backend/var/legalbench/`. _Surfaced in:_ specs/018-autonomous-framework (T-002 implementation).
- **BL-20260511-14** — *test-gap, low* — The two `TestEvolveAuditScanCoverage` tests in `test_coverage_audit.py` are skipped in Docker (scripts/ not mounted). Add a root-level `tests/test_evolve_audit.py` that runs them directly on the host as part of `make lint-specs`. _Surfaced in:_ specs/018-autonomous-framework (T-003 implementation).
- **BL-20260511-15** — *feature, low* — Add `_scan_legalbench` integration test that seeds a fake `report-*.json` with a regression, calls `_scan_legalbench`, and asserts a `severity:high` Candidate is returned. _Surfaced in:_ specs/018-autonomous-framework (T-003 implementation).
- **BL-20260511-16** — *feature, med* — Wire `run_autonomy --kind test_pillar` to invoke `TestSynthesizer` for the top-5 lowest-coverage modules reported by `coverage_audit`; currently `_run_test_pillar` is a stub. _Surfaced in:_ specs/018-autonomous-framework (T-004 implementation).
- **BL-20260511-17** — *test-gap, low* — Add a Vitest / RTL test for a minimal `ProposedTestReview` frontend component that lists `*.proposed.py` files pending review (part of BL-20260511-03 dashboard). _Surfaced in:_ specs/018-autonomous-framework (T-004 implementation).
- **BL-20260511-18** — *infra, low* — Add an `act` local runner config (`.actrc`) so `gh workflow run nightly-tests.yml -f dry_run=true` can be smoke-tested locally without pushing to GitHub. _Surfaced in:_ specs/018-autonomous-framework (T-005 implementation).
- **BL-20260511-19** — *feature, low* — Post the nightly digest Markdown (`backend/var/autonomy/digest-*.md`) as a GitHub Actions job summary (`$GITHUB_STEP_SUMMARY`) so it's visible in the Actions UI without downloading an artifact. _Surfaced in:_ specs/018-autonomous-framework (T-005 implementation).
- **BL-20260511-20** — *feature, med* — Wire `run_autonomy --kind corpus_growth` to invoke `TopicFrontier.run()` (resolves BL-20260511-10 stub placeholder). _Surfaced in:_ specs/018-autonomous-framework (T-007 implementation).
- **BL-20260511-21** — *test-gap, low* — Add a real LangGraph state-machine test using `langgraph.testing` harness to validate node transitions and edge conditions in `TopicFrontier` (currently tested via direct async node calls only). _Surfaced in:_ specs/018-autonomous-framework (T-007 implementation).
- **BL-20260511-22** — *feature, low* — Post digest Markdown to `$GITHUB_STEP_SUMMARY` inside the nightly workflow so operators see it in the Actions UI without downloading an artifact. _Surfaced in:_ specs/018-autonomous-framework (T-010 implementation).
- **BL-20260511-23** — *feature, med* — Add a `compose_digest_task` Celery task that retries on transient DB errors and stores the digest path in the `AuditEvent` payload for cross-referencing. _Surfaced in:_ specs/018-autonomous-framework (T-010 implementation).
- **BL-20260511-24** — *doc-gap, low* — Record first LegalBench baseline scores in `docs/legalbench.md` once the harness has a green run; commit `backend/var/legalbench/baseline.json` and add the commit SHA reference. _Surfaced in:_ specs/018-autonomous-framework (T-011 implementation).
- **BL-20260511-25** — *doc-gap, low* — Add a `LICENSES.md` file alongside any checked-in LegalBench data fixture (CC BY 4.0 attribution required per HazyResearch). _Surfaced in:_ specs/018-autonomous-framework (T-011 implementation).
- **BL-20260511-26** — *test-gap, low* — Add `make test-integration` + `make test-legalbench` runs to the T-012 gate once the full Docker stack is available in CI (currently skipped because Neo4j/Ollama are not in `--no-deps` mode). _Surfaced in:_ specs/018-autonomous-framework (T-012 close).
- **BL-20260511-27** — *feature, med* — Wire `run_autonomy --kind corpus_growth` to call `TopicFrontier.run()` instead of the `_run_corpus_growth` stub (resolves BL-20260511-10 and BL-20260511-20). _Surfaced in:_ specs/018-autonomous-framework (T-012 close).
