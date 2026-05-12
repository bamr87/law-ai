# Spec: Autonomous Testing & Recursive Content-Generation Framework

- **ID**: 018-autonomous-framework
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-05-11
- **Roadmap Epic**: BACKLOG items BL-20260429-09, BL-20260502-04, BL-20260509-04
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — strict AO-SDLC Level 2 retained (§10), provenance & HITL invariants preserved (§4, §5), local-first product runtime preserved (§1).

## 1. Problem & Motivation

Today the repo's only autonomous loop is the weekly `evolve.yml` audit, which only appends BACKLOG candidates from grep + coverage parsing. There is no continuous test-quality loop (the `backend/lawgraph/eval/` LegalBench harness referenced from [docs/legalbench.md](../../docs/legalbench.md) is empty), and there is no recursive content-discovery loop beyond ad-hoc `make ingest` runs of `IngestionScout`. Legal content is effectively unbounded — statutes, regulations, opinions, and citations expand daily across jurisdictions — yet our ingestion frontier is hand-driven.

This spec adds a two-pillar autonomous framework that runs entirely on the local Ollama stack, opens PRs for every code change, and routes every ingested document through the existing HITL quarantine. No new HITL gates are removed, no auto-merge is introduced.

## 2. Goals

- **G1**: Stand up the missing LegalBench harness (Pillar A, "TestPilot") so reasoning regressions are detectable per [docs/constitution.md](../../docs/constitution.md) §3 and §6.
- **G2**: Add a `TestSynthesizer` crew that proposes pytest cases for the lowest-coverage modules, opening a draft PR per nightly run (Pillar A).
- **G3**: Refactor `IngestionScout` and statute scouts behind a `SOURCE_REGISTRY` so adding a new adapter is a single-file change with explicit allow-list gating (Pillar B foundation).
- **G4**: Add a `TopicFrontier` LangGraph workflow that walks Neo4j for orphan citations / under-cited jurisdictions and dispatches *known* sources to the existing `IngestionScout.run_and_commit` path — recursion expands within the registered set, never via freeform web scraping (Pillar B).
- **G5**: Coordinate both pillars under one `AutonomyOrchestrator` (Celery beat + `manage.py run_autonomy`) with a single `AUTONOMY_ENABLED` kill-switch and a daily digest under `backend/var/autonomy/digest-<date>.md`.
- **G6**: Claim and resolve the long-standing autonomy backlog items BL-20260429-09 (agent-self-review CI), BL-20260502-04 (LegalAnalyst onto LegalWorkflow), and BL-20260509-04 (live-network nightly Justia smoke).

## 3. Non-Goals

- **NG1**: No auto-merge of any PR. Every loop ends in either a draft PR (code) or a `PendingReview` row (data).
- **NG2**: No new external data source is added in this spec. Adding a new `SourceAdapter` is its own `/specify` cycle per constitution §5.
- **NG3**: No closed-source LLM fallback. All crew/graph LLM calls go through the existing local Ollama client per constitution §1.
- **NG4**: No freeform web scraping. The `TopicFrontier` only dispatches queries against entries in `SOURCE_REGISTRY` whose name appears in `AUTONOMY_ALLOWED_SOURCES`.
- **NG5**: No promotion to AO-SDLC Level 3 in this spec. Level 2 stays explicit (constitution §10).
- **NG6**: No new frontend dashboard in this MVP — operator surface is the daily digest file plus existing `/api/agents/runs` endpoints. (Frontend dashboard is recorded as a follow-up.)

## 4. User Stories

- As a **reasoning engineer**, I want a single command that runs LegalBench + records a JSON report so I can check whether my prompt change regressed any tracked subset.
- As a **maintainer**, I want a nightly draft PR proposing new tests for our lowest-coverage modules so coverage debt does not silently accumulate.
- As an **ingestion lead**, I want the system to surface "you have 47 unresolved citation targets in the corpus, here are the registered adapters that could resolve them" so my ingestion plan is data-driven.
- As a **HITL reviewer**, I want one digest per day summarizing every autonomy run (PRs opened, BACKLOG items added, docs quarantined, LegalBench delta) so I can audit the loop in five minutes.
- As an **operator**, I want a single env-var (`AUTONOMY_ENABLED=false`) that halts all autonomous activity without redeploying.

## 5. Functional Requirements

- **FR-1**: A `backend/lawgraph/eval/legalbench.py` CLI exists and matches the contract in [docs/legalbench.md](../../docs/legalbench.md): `--subset`, `--model`, `--limit`, `--report`. Default report path is `backend/var/legalbench/<UTC>.json`.
- **FR-2**: The harness emits one OTEL span per item via `lawgraph.core.provenance` and writes a per-item record `{task, item_id, prompt, response, score, latency_ms, model}` into the report.
- **FR-3**: A `backend/lawgraph/eval/coverage_audit.py` module parses `coverage.xml` and returns `(module, pct, missing_lines)` records sorted by deficit. `scripts/evolve_audit.py` consumes it via a thin wrapper (replacing the current stdout-parsing heuristic).
- **FR-4**: A `TestSynthesizer` crew at `backend/lawgraph/agents_runtime/crews/test_synthesizer.py` exposes `run(input: ProposedTestInput) -> ProposedTest` (Pydantic), with a versioned prompt under `agents_runtime/prompts/test_synthesizer.v1.md` and provenance logging on every LLM call.
- **FR-5**: TestSynthesizer output is written as `<module-path>__autonomy.proposed.py` decorated with `@pytest.mark.skip("autonomy-proposed")` so reviewers must explicitly un-skip.
- **FR-6**: A new GitHub Actions workflow `.github/workflows/nightly-tests.yml` (cron `0 6 * * *`) runs `make test-coverage` + `make test-legalbench`, calls `TestSynthesizer` on the worst-coverage module, and opens a draft PR (label `autonomy`) using `peter-evans/create-pull-request` — same pattern as [evolve.yml](../../.github/workflows/evolve.yml).
- **FR-7**: A LegalBench regression of ≥1 pp on any tracked subset (vs. `backend/var/legalbench/baseline.json`) creates a `severity:high` BACKLOG item and fails the workflow.
- **FR-8**: A `backend/lawgraph/ingestionapp/sources/` package exposes `SOURCE_REGISTRY: dict[str, SourceAdapter]`. `CourtListenerAdapter`, `ColoradoStatutesAdapter`, and `StatuteScoutAdapter` are registered, each declaring `name`, `jurisdiction`, `license`, `requires_human_approval`, `rate_limit`, `fetch(query) -> Iterable[RawDoc]`. Existing scout behavior is preserved; the new adapters are thin wrappers.
- **FR-9**: A settings flag `AUTONOMY_ALLOWED_SOURCES: list[str]` (default `[]` in dev, populated explicitly in prod) gates dispatch. The orchestrator refuses to call any adapter whose `name` is not in the list, logging a `policy_violation` provenance event.
- **FR-10**: A management command `python manage.py list_sources` prints the registry as a table (name / jurisdiction / license / allow-listed / rate-limit).
- **FR-11**: A LangGraph workflow `backend/lawgraph/agents_runtime/graphs/topic_frontier.py` exposes nodes `scan_graph` → `prioritize` → `dispatch` → `summarize`, returning a `ContentSweepDigest` Pydantic model. The `dispatch` node ALWAYS routes through `IngestionScout.run_and_commit`; it never writes to Neo4j directly.
- **FR-12**: A `backend/lawgraph/core/autonomy.py` module exposes `run_cycle(kind: Literal["test_pillar","corpus_growth","digest"], cycle_id: UUID | None = None) -> AutonomyRun`, idempotent on `cycle_id`, wrapping every loop in a single audited transaction with start + end provenance events.
- **FR-13**: A `python manage.py run_autonomy --kind {test_pillar,corpus_growth,digest} [--source NAME] [--budget N] [--cycle-id UUID]` command invokes `run_cycle` and exits non-zero on policy violation.
- **FR-14**: Celery beat schedules in `lawgraph.celery`: `autonomy-content-sweep` (`corpus_growth`) every 6h (budget 25 items), `autonomy-nightly-tests` (`test_pillar`) daily at 06:00 UTC, `autonomy-daily-digest` (`digest`) daily at 07:00 UTC. The existing `.github/workflows/evolve.yml` continues to drive the weekly evolve run from CI; the beat entries are the local-stack equivalent.
- **FR-15**: A daily `compose_digest` task writes `backend/var/autonomy/digest-<YYYY-MM-DD>.md` enumerating PRs opened, BACKLOG items appended, docs quarantined, and the LegalBench delta versus baseline.
- **FR-16**: A global `AUTONOMY_ENABLED` settings flag (default `False`) short-circuits `run_cycle` with a single provenance event when false; no Celery dispatch, no PR action, no Neo4j read.
- **FR-17**: New Makefile targets `autonomy-up`, `autonomy-status`, `autonomy-stop` shell into the `worker` container to start/inspect/stop the beat schedule (Docker-first per AGENTS.md).

## 6. Non-Functional Requirements

- **NFR-PERF-1**: A single `content_sweep` cycle with `--budget 25` completes in <10 minutes against the local docker stack on a developer laptop (Mistral 7B q4_K_M).
- **NFR-PERF-2**: A `nightly_tests` cycle with `--limit 20` LegalBench items per task completes in <30 minutes on the same hardware.
- **NFR-SEC-1**: All adapter HTTP calls go through `httpx` + `tenacity` retries + per-adapter `rate_limit`; no raw `requests`. Adapter `fetch` results are validated by Pydantic before reaching the orchestrator.
- **NFR-AUDIT-1**: Every `run_cycle` start, end, and dispatched LLM/tool call is logged via `lawgraph.core.provenance`. Every adapter dispatch records `{adapter_name, query, items_returned, items_quarantined}`.
- **NFR-HITL-1**: `requires_human_approval=True` on any adapter forces every `RawDoc` it returns into `PendingReview` regardless of confidence — matches constitution §5.
- **NFR-AUDIT-2**: The daily digest is the canonical human-review surface. It MUST link every PR by URL and every quarantined doc by `PendingReview.id` so a reviewer can navigate from digest → action in one hop.
- **NFR-SEC-2**: `AUTONOMY_ENABLED` defaults to `False`; production deployments must set it explicitly. Documented in [docs/local-ai.md](../../docs/local-ai.md).

## 7. Data Model Impact

No new Neo4j node labels or edge types. No new Postgres tables in this MVP — `AutonomyRun` records are written to `audit.AuditEvent` with `event_type='autonomy_cycle'` and a JSON payload `{cycle_id, kind, started_at, ended_at, status, summary}`.

A future spec may promote `AutonomyRun` to its own table once the digest needs richer querying (recorded as a follow-up). All existing constraints from constitution §4 remain — no new node-creation paths bypass `source` / `confidence` / `ingest_timestamp`.

## 8. API Surface

No new public REST endpoints in this MVP. Internal Django management commands:

- `python manage.py list_sources` — prints registered adapters.
- `python manage.py run_autonomy --kind {test,content,evolve} [--source NAME] [--budget N] [--cycle-id UUID]` — run one cycle.

The existing `/api/agents/runs/` endpoint already surfaces `audit.AuditEvent` rows, so the orchestrator's `autonomy_cycle` events are queryable through it without new routes.

## 9. Agent / Crew Impact

New entries to add to [docs/agent-roles.md](../../docs/agent-roles.md):

- **TestSynthesizer** — proposes pytest cases for low-coverage modules. Tools: `coverage_audit.lowest_coverage_module`, file-read on the target module. Output: `ProposedTest` Pydantic model. `requires_human_approval=True` (output always goes into a `*.proposed.py` file behind `@pytest.mark.skip`).
- **TopicFrontier** — LangGraph workflow that walks Neo4j and dispatches registered adapters. Tools: `core.neo4j.queries.list_orphan_citations`, `SOURCE_REGISTRY`. `requires_human_approval=False` at the workflow level because every dispatched doc still hits `IngestionScout`'s confidence gate.

No changes to existing agents (`LegalAnalyst`, `PrecedentHunter`, `IngestionScout`) in this spec. BL-20260502-04 (backfill `LegalAnalyst` onto `LegalWorkflow`) is claimed but its actual code change is gated on the LegalBench baseline landing first; recorded as a follow-up if it does not fit in this cycle.

## 10. Acceptance Criteria

- **AC-1**: `make test-legalbench` exits 0 inside the backend container, writes a JSON report under `backend/var/legalbench/<UTC>.json`, and the report contains at least one record per requested subset (FR-1, FR-2).
- **AC-2**: Running `python manage.py run_autonomy --kind test --limit 5` writes a `*.proposed.py` file under `backend/tests/autonomy/proposed/` containing at least one `@pytest.mark.skip("autonomy-proposed")`-decorated function (FR-4, FR-5).
- **AC-3**: Running `python manage.py run_autonomy --kind content --source unknown_source` exits non-zero and emits a provenance event with `event_type='policy_violation'` (FR-9, NFR-AUDIT-1).
- **AC-4**: Running `python manage.py run_autonomy --kind content --source courtlistener --budget 3` (with `AUTONOMY_ENABLED=True`) creates **zero** new `:Case` nodes that did not pass through `IngestionScout.run_and_commit`'s confidence gate (FR-11, NFR-HITL-1). Verified by an integration test that asserts every new node carries the `IngestionScout` `agent_version`.
- **AC-5**: With `AUTONOMY_ENABLED=False`, `python manage.py run_autonomy --kind content` exits 0, makes zero HTTP calls, makes zero Celery dispatches, and emits exactly one provenance event with `event_type='autonomy_disabled'` (FR-16).
- **AC-6**: `python manage.py list_sources` prints exactly three rows for `courtlistener`, `colorado_statutes`, `statute_scout` and marks each one `allow-listed=False` by default (FR-8, FR-10).
- **AC-7**: After one nightly cycle in CI, `backend/var/autonomy/digest-<date>.md` exists and contains sections "PRs opened", "BACKLOG items appended", "Docs quarantined", "LegalBench delta" with at least the headers populated (FR-15, NFR-AUDIT-2).
- **AC-8**: A simulated LegalBench regression of 2 pp (forced via a pytest fixture) causes `nightly-tests.yml` to exit non-zero AND adds one `severity:high` BACKLOG item via `evolve_audit.py` (FR-7).
- **AC-9**: `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py` both exit 0 after this spec lands.

## 11. LegalBench Impact

- Tasks affected: none in this spec — TestPilot only **measures** LegalBench, it does not change reasoning logic.
- Expected delta: 0 pp ± 0 pp on `core_reasoning` and `precedent_retrieval`. The very first run establishes `backend/var/legalbench/baseline.json`; no prior baseline exists.
- The baseline JSON commit is gated on `backend/var/legalbench/LICENSES.md` landing first (per-task source + license enumeration). Documented in plan §3.

## 12. Risks & Open Questions

- **R-1** *(med)*: LegalBench dataset size + Ollama latency may exceed the 30-min nightly budget on weaker hardware. Mitigation: `--limit 20` per task by default; CI runs the full set monthly. — accepted.
- **R-2** *(med)*: A misconfigured `AUTONOMY_ALLOWED_SOURCES` could allow a Celery worker to hammer an external API. Mitigation: per-adapter `rate_limit` enforced by `httpx` + `tenacity`; orchestrator caps `--budget` at 100. — accepted.
- **R-3** *(low)*: TestSynthesizer may propose nonsense tests, polluting PR review queues. Mitigation: `*.proposed.py` + `@pytest.mark.skip("autonomy-proposed")` make every proposal opt-in; never executed by default. — accepted.
- **R-4** *(low)*: LegalBench upstream license drift could force us to drop tasks mid-baseline. Mitigation: `LICENSES.md` manifest is reviewed at every spec touching the harness. — accepted.
- **R-5** *(low)*: BL-20260502-04 (LegalAnalyst onto LegalWorkflow) may not fit in this cycle. Mitigation: pre-declared as a follow-up to BACKLOG; spec scope does not require it. — accepted.

## 13. Out of Scope / Follow-ups

- Read-only `frontend/app/autonomy/` dashboard with Vitest test (will be a separate spec, recorded as `BL-20260511-NN`).
- Auto-merge classes for low-risk PRs (would require a constitution amendment per §10).
- Promotion of `AutonomyRun` to a dedicated Postgres table.
- Multi-jurisdictional adapter additions (each new source = new spec per constitution §5).
- Streaming digest to Slack/email (out of MVP).
