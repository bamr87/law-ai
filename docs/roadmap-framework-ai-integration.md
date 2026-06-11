# Roadmap — Framework & AI Integration Improvements

- **Status**: adopted 2026-06-11 (Phase 1 shipped via [specs/024-unified-llm-client](../specs/024-unified-llm-client/spec.md))
- **Scope**: closes the gap between the platform's mature governance/infra layers and its incomplete AI core.
- **Constitution**: Ollama stays the product runtime LLM ([constitution](constitution.md) §1); every phase keeps `core.provenance` in the loop (§4); HITL gates preserved (§5).

## Why

A full-repo review (backend AI layer, framework/infra, frontend) found a consistent picture: provenance/audit, CI gates, auth, and Docker-first dev are mature, but the AI core was hollow:

1. The GraphRAG retriever always returned `[]` (`agents_runtime/graphs/legal_workflow.py`), forcing the refusal path on every analysis.
2. LLM calls were scattered across four HTTP patterns (LangChain `ChatOllama`, httpx ×2, urllib ×2) with no retry, no pooling, and streaming disabled everywhere.
3. PrecedentHunter returns a hardcoded mock; LegalAnalyst kept a legacy mock path.
4. The LegalBench harness runs on synthetic stubs with no committed baseline and an opt-in CI gate.
5. WebSocket streaming is half-done (spec 022): events emit only after `asyncio.gather`; the frontend polls every 5s with no WS client.
6. Framework gaps: mypy `--strict` advisory in CI, endpoint logic inline in `urls.py`, frontend `strict: false` with hand-written API types and the API key in the browser bundle, missing HITL admin actions, no rate limiting.

## Architectural decisions

| Decision | Choice | Why |
|---|---|---|
| Unified LLM client | `ollama` Python package (`AsyncClient`/`Client`) wrapped once in `backend/lawgraph/core/llm/` | Already a dependency; httpx-based (pooling for free); native `stream=True` + `embed()`; one pattern replaces five hand-rolled ones |
| Vector store | Neo4j 5 native vector indexes (not Chroma) | `neo4j:5-community` with apoc+GDS already runs; migration `007_fulltext_indexes.cypher` covers the same labels; hybrid retrieval in one Cypher round-trip, no new service, no ID-sync problem |
| Provenance | every LLM call logs an `llm_call` event via `core/audit_jsonl.py` + OTEL span; new graph nodes use `@logged_node` | constitution §4 |
| Sequencing | retrieval ships flagged → LegalBench baseline lands → defaults flip & mocks deleted | respects BL-20260511-06's own gate |

## Phases

Dependency graph: **1 → 2 → 3; 1 → 4; 4 → 5 → 6** (Phases 2–3 and 4 can run in parallel after Phase 1).

### Phase 1 — Unified LLM client + prompt registry ✅ (specs/024)

One audited, retrying, streaming-capable path to Ollama; prompts loaded from versioned files.

- `backend/lawgraph/core/llm/` — `LLMClient` (generate / generate_stream / chat / embed / generate_sync), exponential-backoff retry, per-call provenance, `LLMError` hierarchy.
- `LLMClientAdapter` replaces `ChatOllama` in `legal_workflow._default_llm_factory` (protocol-compatible, no node changes).
- All five scattered call sites migrated: `lsat_content_author.py`, `lsat/services/tutor.py`, `topic_frontier.py`, `test_synthesizer.py`, `eval/legalbench.py`.
- `agents_runtime/prompts/loader.py` — versioned prompt registry; the previously-unwired `prompts/legal_workflow/{retrieve,analyze}.md` now drive the workflow nodes.
- Verify: `make test-backend`, `make lint`, `make typecheck`; grep shows no `api/generate`/`ChatOllama` outside `core/llm`.

### Phase 2 — GraphRAG retrieval (flagged) + embeddings + Cypher migration runner

Real hybrid retrieval behind `GRAPHRAG_RETRIEVAL_ENABLED` (default off until Phase 3 proves it).

- Cypher migration runner recording `(:_Migration {id})` (BL-20260511-01; supersedes BL-20260509-02) — gates the rest.
- `008_vector_indexes.cypher` on the labels covered by 007's fulltext indexes; embed backfill management command via `LLMClient.embed()` (`OLLAMA_EMBED_MODEL`, e.g. `nomic-embed-text`); embed-at-ingest hook.
- `core/neo4j/retrieval.py` — vector + fulltext RRF merge + 1-hop citation expansion (reuses `queries.py`, `citation_resolver.py`); wired into `_default_retriever`.
- Real `PrecedentHunter` on the same module (BL-20260430-04); remove unused `chromadb` dep (BL-20260611-03).
- Specs: `specs/025-cypher-migration-runner`, `specs/026-graphrag-retrieval`. Verify: `make test-integration`, idempotency test on the migration runner.

### Phase 3 — LegalBench baseline → flip AI defaults

- Real pinned dataset cached under `backend/var/legalbench/` (synthetic stubs stay as offline-CI fallback); scoring upgrades incl. citation-faithfulness via `citation_resolver`.
- Commit `baseline.json` (BL-20260511-24); `make test-legalbench` compares against it with a regression threshold; CI gate becomes path-triggered for `agents_runtime/` + `prompts/`.
- Flip `GRAPHRAG_RETRIEVAL_ENABLED=True`; delete LegalAnalyst's legacy mock path (BL-20260511-06, closes BL-20260430-03 / BL-20260502-04).
- Spec: `specs/027-legalbench-baseline-gate`.

### Phase 4 — Progressive streaming + analysis persistence

- Progressive `agent_step` + token-level `agent_token` events from `analysis/urls.py` using `LLMClient.generate_stream` (BL-20260602-05, BL-20260611-02).
- `Analysis` ORM model + history endpoint (BL-20260429-25).
- Frontend WS client for `/ws/agents/{analysis_id}` replacing the 5s poll (BL-20260602-06); Next.js API proxy removing `NEXT_PUBLIC_AGENT_API_KEY` from the bundle (BL-20260430-07).
- Spec: `specs/028-progressive-streaming` (extends 022).

### Phase 5 — API framework hardening

- Extract inline endpoint logic from `urls.py` into `views.py` + serializers (analysis/graph/lsat/agentsapi); drf-spectacular OpenAPI + frontend type codegen; `strict: true` in `frontend/tsconfig.json`.
- Enforce mypy `--strict` in CI (drop `continue-on-error`, BL-20260429-04); per-token rate limiting (BL-20260503-12); prod startup guard (BL-20260430-12).
- Spec: `specs/029-api-views-openapi`.

### Phase 6 — HITL completion + E2E safety net

- Django admin approve/reject/re-extract on `PendingReview` + Celery apply tasks (BL-20260503-10); analysis HITL queue reusing the LSAT proposal UI pattern.
- Playwright E2E suite (`make test-e2e`): HITL flow + streaming-analysis happy path (BL-20260503-17).
- Spec: `specs/030-hitl-admin-e2e` (builds on spec 023).

## Tracking

Every phase lands as an AO-SDLC spec package; follow-ups append to [BACKLOG.md](../BACKLOG.md) per `scripts/backlog_lint.py`. Update the phase status markers here as specs ship.
