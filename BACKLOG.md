# LawGraph AI — Backlog

> **Append-only** register of follow-ups discovered during implementation. Every `/implement` cycle MUST append discovered work here in addition to closing the current task. Items graduate from this list into `specs/NNN-*/` via `/specify`.
>
> **Format**: One bullet per item, kebab-case ID, status, brief context, link to the spec/PR that surfaced it.

## Conventions

| Field        | Notes                                                                  |
| ------------ | ---------------------------------------------------------------------- |
| `id`         | `BL-YYYYMMDD-NN` — the date discovered + an ordinal                    |
| `status`     | `open` / `claimed-by:specs/NNN` / `wontfix` (with reason) / `done`     |
| `kind`       | `feature` / `refactor` / `tech-debt` / `test-gap` / `doc-gap` / `infra`|
| `severity`   | `low` / `med` / `high`                                                 |
| `surfaced-in`| Spec or PR that discovered it                                          |

## Triage rules

1. New items go to **Open**. Promotions go to **Claimed**. Resolved items move to **Done** (kept for audit; never delete).
2. Items unclaimed > 60 days get reviewed at the next `/specify` cycle and either closed `wontfix` or escalated.
3. CI gate ([scripts/backlog_lint.py](scripts/backlog_lint.py)) enforces format and forbids deletion of historical entries.

---

## Open

- **BL-20260503-09** — *feature, med* — Real Channels producers for `/ws/agents/{run_id}` so `LegalAnalyst`/`PrecedentHunter` progress streams to the consumer skeleton landed by spec 011 T-010. Resolves overlap with BL-20260429-24. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-10** — *feature, med* — Django admin actions on `ingestionapp.PendingReview` (approve/reject/re-extract) plus matching `core.tasks` to apply the decision back to Neo4j. Resolves overlap with BL-20260429-15. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-11** — *feature, low* — `/agents/runs/{trace_id}` view backed by `audit.AuditEvent` joined on `trace_id` so the spec-003 dashboard can drill into a single run. Resolves overlap with BL-20260429-14. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-12** — *feature, med* — Per-token rate limiting via `django-ratelimit` keyed on `request.auth.key_hash`. Resolves overlap with BL-20260430-09. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-13** — *feature, med* — JWT/OAuth on top of `core.ApiToken` (revives `python-jose` + `passlib` deps under the new `[future-auth]` extra). _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-14** — *infra, low* — Periodic Celery beat job that runs `scripts/backlog_lint.py` + `scripts/spec_validator.py` and opens a triage issue when stale. Resolves overlap with BL-20260429-09. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-15** — *refactor, low* — Retire raw `asyncpg` calls outside the LangGraph checkpointer in favor of Django's connection pool now the ORM is on hand. Partially resolves BL-20260429-17. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-16** — *doc-gap, med* — Flesh out `docs/security.md` with the API-token rotation procedure, scope matrix, and `seed_api_keys` runbook. Resolves BL-20260430-10. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-17** — *test-gap, med* — Playwright end-to-end test exercising the Django admin HITL flow against a docker stack (login → list quarantine → approve → assert Neo4j commit). _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-18** — *doc-gap, low* — Author `docs/django-conventions.md` capturing settings split, `settings_proxy` usage, `acreate` discipline, Channels routing, and Celery task naming patterns. _Surfaced in:_ specs/011-django-backend.
- **BL-20260503-19** — *infra, high* — ~~Hand-edit `lawgraph/ingestionapp/migrations/0001_initial.py` to use `RunSQL` with verbatim DDL from `app/db/postgres_migrations/{001_pending_review,002_pg_trgm}.sql` and a `state_operations`/`database_operations` split, so live Postgres rows survive cutover.~~ **(resolved 2026-05-03)**: migration now wraps `SeparateDatabaseAndState(state_operations=[CreateModel(PendingReview)], database_operations=[RunPython(_create_pending_review)])`; on Postgres the RunPython executes the legacy spec-004 DDL with `IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS reviewed_at/approved` + `CREATE EXTENSION IF NOT EXISTS pg_trgm` so existing rows are adopted in place; on SQLite (test fixture) it falls back to portable DDL. Lock-in tests in `backend/tests/ingestion/test_initial_migration.py`. _Surfaced in:_ specs/011-django-backend implementation.
- **BL-20260503-20** — *refactor, med* — ~~Refactor `lawgraph/ingestionapp/services/scout.py` to delegate quarantine writes to the `quarantine_extraction` Celery task (currently still uses inline asyncpg + JSONL).~~ **(resolved 2026-05-03)**: `_quarantine_postgres` (asyncpg) replaced with `_quarantine_via_celery` that builds a payload dict and calls `quarantine_extraction.delay(...)`; the Celery task is now the sole writer for `PendingReview` + `AuditEvent`; JSONL fallback preserved when dispatch raises. New tests `test_low_confidence_routes_to_postgres_when_available`, `test_quarantine_via_celery_dispatches_with_expected_payload`, and `test_scout_no_longer_uses_inline_asyncpg` cover the contract. Closes T-011 of spec 011. _Surfaced in:_ specs/011-django-backend implementation.
- **BL-20260503-21** — *test-gap, high* — ~~Re-establish ≥75% backend coverage on the Django app~~ **(resolved 2026-05-03)**: backend at **84.08%** (126 tests). Added unit tests for `agentsapi.consumers.AgentRunConsumer` (Channels), `ingestionapp.tasks.quarantine_extraction` (Celery), and `seed_api_keys` + `ensure_checkpointer` management commands. _Surfaced in:_ specs/011-django-backend implementation.
- **BL-20260503-22** — *test-gap, med* — ~~Triage and fix the pre-existing `__tests__/components/LsatLab.test.tsx` long-passage assertion failure carried through the Django refactor so `npm test -- --run` is fully green again.~~ **(resolved 2026-05-03)**: `npm test -- --run` is fully green (5 files / 21 tests, including all 5 LsatLab cases). _Surfaced in:_ specs/011-django-backend implementation.
- **BL-20260503-23** — *refactor, low* — Strip the dead-code FastAPI path from `lawgraph/core/telemetry.py` (TYPE_CHECKING import + `FastAPIInstrumentor.instrument_app` branch) and replace with `DjangoInstrumentor` so OTEL spans cover the new ASGI app. Sweep remaining historical FastAPI/uvicorn references in core docstrings. _Surfaced in:_ specs/011-django-backend implementation.
- **BL-20260503-24** — *infra, med* — ~~Wire Django static files for the dockerized stack~~ **(resolved 2026-05-03)**: added `whitenoise` dep + `WhiteNoiseMiddleware` + `CompressedManifestStaticFilesStorage`; `collectstatic --noinput` now runs in the backend container start command. _Surfaced in:_ specs/011-django-backend container validation.
- **BL-20260503-25** — *infra, low* — Document the Postgres major-version pin in `docker-compose.yml` (currently `16-alpine` because the existing dev volume was initialized on pg16) and add a `make reset-db` runbook for operators that need to bump. _Surfaced in:_ specs/011-django-backend container validation.

- **BL-20260503-01** — *feature, med* — Version the LSAT tutor prompt under `prompts/lsat-tutor/v1.md` and load it through `core.provenance` so prompt drift is auditable across `lsat_tutor` events. _Surfaced in:_ specs/005-lsat-lab refactor (multi-section + AI tutor).
- **BL-20260503-02** — *feature, med* — Expand RC + LG banks to ≥10 passage/game sets each with editorial review and source attribution; add CI schema check for `passage_id` linkage. _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-03** — *feature, med* — SSE/streaming variant of `POST /api/lsat/tutor` so the frontend can stream coaching tokens from Ollama instead of waiting for the full JSON. _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-04** — *feature, low* — Add the LSAT Writing Sample (WS) section: rubric viewer, exemplar prompts, and a self-grading rubric in the tutor. _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-05** — *feature, med* — Persist per-user LSAT attempt history (Postgres) once auth lands so `/api/lsat/stats` can return per-learner accuracy + spaced-repetition queues. _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-06** — *feature, low* — Surface `phoenix_trace_url` + `langgraph_thread_id` on tutor responses (mirrors BL-20260502-05 for analysis). _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-07** — *test-gap, low* — Add a Vitest+MSW test that exercises the `used_llm=false` fallback rendering path in `LsatLab` (offline tutor banner). _Surfaced in:_ specs/005-lsat-lab refactor.
- **BL-20260503-08** — *doc-gap, low* — Refresh `specs/005-lsat-lab/spec.md` to cover the multi-section + concept-catalog + tutor scope and link the new `/api/lsat/{sections,concepts,passages,tutor}` endpoints. _Surfaced in:_ specs/005-lsat-lab refactor.

- **BL-20260502-01** — *feature, med* — Self-host LangGraph API + Studio container (`langchain/langgraph-api`) so designers can step through `LegalWorkflow` runs visually. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-02** — *infra, med* — Linux + NVIDIA workstation tier: GPU runtime in compose, optional vLLM service, default model upgraded to `llama3.1:70b-q4_K_M`. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-03** — *infra, low* — Server / multi-GPU tier with Prometheus + Grafana for token/sec, GPU utilization, queue depth. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-04** — *feature, med* — Backfill `LegalAnalyst` (BL-20260430-03) and `PrecedentHunter` (BL-20260430-04) onto `LegalWorkflow` once parity proven on LegalBench. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-05** — *feature, low* — `AgentTrace.tsx` surfaces `phoenix_trace_url` + `langgraph_thread_id` returned by `/api/analysis` so users can deep-link from the UI. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-06** — *infra, low* — Air-gapped deployment hardening: bundle pre-pulled Ollama models into a tarball + offline install script. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-07** — *feature, low* — Langfuse fallback path if Phoenix license terms change; abstract the OTEL exporter behind `settings.OBSERVABILITY_BACKEND`. _Surfaced in:_ specs/010-local-ai-stack.
- **BL-20260502-08** — *test-gap, low* — CI matrix entry that runs the spec-010 Postgres+Ollama integration test (currently only locally executable). _Surfaced in:_ specs/010-local-ai-stack.

- **BL-20260429-24** — *feature, med* — Stream agent trace events to the `/analysis` UI via SSE so users see `LegalAnalyst` → `PrecedentHunter` progress instead of waiting for a single JSON response. _Surfaced in:_ specs/007-analysis-studio.
- **BL-20260429-25** — *feature, med* — Persist analyses (request + response + trace_ids) in Postgres so users can revisit a run by `analysis_id` and the `/agents/runs/{trace_id}` drill-down (BL-20260429-14) can join across child traces. _Surfaced in:_ specs/007-analysis-studio.
- **BL-20260429-26** — *feature, low* — "Save & share" — let signed-in users bookmark an analysis with a slug and produce a shareable URL. _Surfaced in:_ specs/007-analysis-studio.
- **BL-20260429-27** — *test-gap, low* — Playwright smoke test hitting `/analysis` end-to-end against a Docker stack (form fill → result render → trace ID copy). _Surfaced in:_ specs/007-analysis-studio.

- **BL-20260429-21** — *test-gap, med* — Docker-backed integration test for `app.db.graph_queries.neighborhood` against a real Neo4j; mirrors BL-20260429-10. _Surfaced in:_ specs/006-knowledge-graph.
- **BL-20260429-22** — *feature, med* — Add a shortest-path endpoint (`/api/graph/path?from=&to=`) so the UI can highlight precedent chains between two cases. _Surfaced in:_ specs/006-knowledge-graph.
- **BL-20260429-23** — *feature, low* — UI filters for the case picker (court, date range) and a sidebar inspector showing selected-node full properties + source URL. _Surfaced in:_ specs/006-knowledge-graph.

- **BL-20260429-18** — *feature, med* — Author "LR Tutor" agent that produces personalized rationales per LSAT attempt using the user's reasoning trace. _Surfaced in:_ specs/005-lsat-lab.
- **BL-20260429-19** — *feature, low* — Expand `backend/app/lsat/data/lr_bank.json` to ≥ 50 items with editorial review; add a CI check that validates schema + label set. _Surfaced in:_ specs/005-lsat-lab.
- **BL-20260429-20** — *feature, low* — Add Reading Comprehension + Logic Games question types to LSAT Lab (extend `Question.type` enum + add bank files). _Surfaced in:_ specs/005-lsat-lab.

- **BL-20260430-01** — *refactor, med* — Resolve TODO in backend/app/main.py. Comment: "Initialize Neo4j, Postgres, Redis, Ollama clients"
- **BL-20260430-03** — *refactor, med* — Resolve TODO in backend/app/agents/crews/legal_analyst.py. Comment: "Implement real GraphRAG retrieval + LLM call"
- **BL-20260430-04** — *refactor, med* — Resolve TODO in backend/app/agents/crews/precedent_hunter.py. Comment: "Real Cypher + vector search"
- **BL-20260430-06** — *doc-gap, low* — Author missing doc docs/legalbench.md. Referenced by AGENTS.md but file does not exist.

- **BL-20260429-01** — *test-gap, med* — Add docker-backed integration tests for `IngestionScout.run_and_commit` covering AC-3 and NFR-IDEMPOTENT-1 (currently marked `@pytest.mark.integration` but no green run recorded). _Surfaced in:_ specs/001-ingest-courtlistener-opinions.
- **BL-20260429-03** — *feature, low* — Reintroduce Blackstone NER for `_extract_entities` once we have a lazy-loading shim that doesn't break test startup time. _Surfaced in:_ specs/001-ingest-courtlistener-opinions.
- **BL-20260429-04** — *infra, med* — `mypy app/ --strict` is `continue-on-error: true` in CI; tighten once new modules are annotated end-to-end. _Surfaced in:_ .github/workflows/ci.yml.
- **BL-20260429-06** — *test-gap, low* — Add a smoke test that runs `scripts/ingest_sample.py --dry-run --limit 3` against `respx`-mocked CourtListener to lock in CLI contract. _Surfaced in:_ specs/001-ingest-courtlistener-opinions T-004.
- **BL-20260429-07** — *doc-gap, low* — Document the `/health` JSON contract in `docs/api.md` (file does not yet exist). _Surfaced in:_ specs/001-ingest-courtlistener-opinions T-005.
- **BL-20260429-08** — *infra, low* — `backend/pyproject.toml` pulls `blackstone @ git+...` — slows CI installs. Move to `[project.optional-dependencies].nlp` and gate behind a feature flag. _Surfaced in:_ .github/workflows/ci.yml.
- **BL-20260429-09** — *feature, med* — Wire a periodic CI job ("agent-self-review") that runs `scripts/backlog_lint.py` plus a small LLM prompt to flag stale items (>60 days) for triage. _Surfaced in:_ this file.
- **BL-20260429-10** — *test-gap, med* — Add Docker-backed integration test for `densify_extraction` against a real Neo4j (currently only `FakeAsyncSession`). _Surfaced in:_ specs/002-resolve-citations-to-cases.
- **BL-20260429-11** — *feature, med* — Backfill script `scripts/densify_existing.py` that re-runs `densify_extraction` over historical `:Case` nodes once aliases are populated. _Surfaced in:_ specs/002-resolve-citations-to-cases.
- **BL-20260429-12** — *refactor, low* — Make `head(collect(c.id))` deterministic by adding a secondary `ORDER BY c.id` clause inside `RESOLVE_CITATIONS_CYPHER`; matters when two cases share an alias. _Surfaced in:_ specs/002-resolve-citations-to-cases.
- **BL-20260429-14** — *feature, med* — Add a single-run drill-down view (`/agents/runs/{trace_id}`) showing full input/output, sources, and prompt template version. _Surfaced in:_ specs/003-agent-ops-dashboard.
- **BL-20260429-15** — *feature, med* — Add HITL action endpoints (`approve` / `reject`) so reviewers can resolve quarantined items from the dashboard. _Surfaced in:_ specs/003-agent-ops-dashboard.
- **BL-20260429-16** — *infra, low* — Replace polling with WebSocket push when concurrent reviewers > 5 (current 5 s polling is wasteful at scale). _Surfaced in:_ specs/003-agent-ops-dashboard.
- **BL-20260429-17** — *infra, low* — Introduce a shared `asyncpg.Pool` in `app.db.postgres` so HITL writes (and future routes) reuse connections instead of doing per-call `connect`/`close`. _Surfaced in:_ specs/004-async-quarantine-postgres.

- **BL-20260430-07** — *feature, med* — Move `NEXT_PUBLIC_AGENT_API_KEY` out of the browser bundle by routing all browser→backend calls through a Next.js API proxy that injects the header server-side. _Surfaced in:_ specs/008-agent-api-auth.
- **BL-20260430-09** — *feature, med* — Add per-key rate limiting on the API-key-gated routers (today an attacker can brute-force at line speed once a key is configured). _Surfaced in:_ specs/008-agent-api-auth.
- **BL-20260430-10** — *doc-gap, low* — Author `docs/security.md` documenting the API-key model, rotation procedure, and the per-router fallback chain shipped in spec 009. _Surfaced in:_ specs/008-agent-api-auth.
- **BL-20260430-11** — *test-gap, low* — Add a Playwright smoke test that toggles `AGENT_API_KEY`/`NEXT_PUBLIC_AGENT_API_KEY` and verifies all four pages (`/agents`, `/analysis`, `/graph`, `/lsat`) load end-to-end against a Docker stack. _Surfaced in:_ specs/009-extend-api-auth.
- **BL-20260430-12** — *infra, low* — Have `app/main.py` lifespan refuse to start when `ENVIRONMENT="production"` and `AGENT_API_KEY` is unset (today it only warns). _Surfaced in:_ specs/009-extend-api-auth.
- **BL-20260430-13** — *doc-gap, low* — Document the per-router fallback chain (`<ROUTER>_API_KEY` → `AGENT_API_KEY`) in [docs/architecture.md](docs/architecture.md), including a short table mapping routes → settings. _Surfaced in:_ specs/009-extend-api-auth.

## Claimed

_(none yet)_

## Done

- **BL-20260430-08** — *feature, high* — Extended `require_api_key` into a `make_api_key_dep(*setting_names)` factory and gated `/api/analysis`, `/api/graph/*`, `/api/lsat/*` with per-router keys (`ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY`) that fall back to `AGENT_API_KEY`. Frontend consolidated onto `apiFetch` so a single `NEXT_PUBLIC_AGENT_API_KEY` covers every gated call. 11 new tests, backend coverage 90.55%. _Shipped in:_ specs/009-extend-api-auth.
- **BL-20260429-13** — *feature, high* — Added shared API-key auth (`X-API-Key` + `secrets.compare_digest`) gating `/api/agents/*`. Default-open posture preserved when `AGENT_API_KEY` is unset; startup warning logged outside `ENVIRONMENT=development`. _Shipped in:_ specs/008-agent-api-auth (extended in 009).

- **BL-20260430-05** — *refactor, med* — Replaced GraphViewer.tsx Cytoscape stub with a real dynamically-imported Cytoscape canvas wired to `/api/graph/neighborhood`. _Shipped in:_ specs/006-knowledge-graph.
- **BL-20260429-02** — *refactor, med* — Converted `IngestionScout._quarantine` and `_quarantine_postgres` to native async (no more `asyncio.run` inside the async ingestion loop). HITL items now reach Postgres in production; JSONL becomes a true failure-only fallback. scout.py coverage 81.60% → 90.57%. _Shipped in:_ specs/004-async-quarantine-postgres.
- **BL-20260430-02** — *refactor, med* — Replaced TODO in backend/app/main.py by mounting the new `/api/agents` router (registry, runs, backlog, specs). _Shipped in:_ specs/003-agent-ops-dashboard.
- **BL-20260429-05** — *feature, high* — Resolved citations to existing `Case` nodes via `app.db.citation_resolver` (spec 002, 6 unit tests, 79.51% coverage). _Shipped in:_ specs/002-resolve-citations-to-cases.

