# Spec: Ingest CourtListener Opinions

- **ID**: 001-ingest-courtlistener-opinions
- **Status**: draft
- **Owner**: @bamr87
- **Created**: 2026-04-29
- **Roadmap Epic**: MVP — first real data source for the knowledge graph
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

LawGraph's reasoning agents (`LegalAnalyst`, `PrecedentHunter`) need a populated Neo4j graph of real US case law to be useful. Today the graph is empty: there is no ingestion pipeline, only a stub `Ingestion Scout` row in [docs/agent-roles.md](../../docs/agent-roles.md). [CourtListener](https://www.courtlistener.com/help/api/rest/) provides a free, well-documented REST API over US federal and state opinions and is the obvious first source. Without it we cannot establish a LegalBench baseline (per [docs/constitution.md](../../docs/constitution.md) §10) or demo the Analysis Studio against real data.

## 2. Goals

- G1: Ingest a bounded set of CourtListener opinions (default 500) into Neo4j with full provenance.
- G2: Extract citations via Eyecite and create `Case`-`CITES`->`Case` edges where targets are already in the graph.
- G3: Make the pipeline runnable from the existing `Ingest Sample Data` VS Code task and `make ingest` (new target).
- G4: Establish the `IngestionScout` agent class as the canonical implementation pattern for future data-source crews.

## 3. Non-Goals

- NG1: Full historical backfill (>500 opinions). A separate spec will cover paginated, resumable bulk ingest.
- NG2: Non-CourtListener sources (CAP, legislation.gov.uk, EUR-Lex).
- NG3: PDF OCR — CourtListener already provides plain text; we trust it.
- NG4: UI for triggering or monitoring ingestion. CLI / task only for now.

## 4. User Stories

- As a **LawGraph developer**, I want to run one command and have a populated Neo4j graph, so that I can demo and test the reasoning agents locally.
- As a **legal researcher**, I want every ingested case to carry its CourtListener URL, ingest timestamp, and confidence score, so that I can audit any downstream analysis.
- As a **maintainer**, I want low-confidence extractions to be flagged for human review, so that we never silently ingest garbage into the graph.

## 5. Functional Requirements

- **FR-1**: A `CourtListenerClient` in `backend/app/ingestion/courtlistener.py` fetches opinions via the public `/api/rest/v4/opinions/` endpoint, with `httpx` + `tenacity` retry/backoff.
- **FR-2**: An `IngestionScout` agent in `backend/app/ingestion/scout.py` accepts a raw opinion payload and produces an `ExtractionResult` Pydantic model containing `citations`, `entities`, `holding_summary`, `confidence`.
- **FR-3**: `IngestionScout.run_and_commit(payload)` writes a `Case` node to Neo4j and `CITES` edges to any already-present targets, returning `committed=True` only after the Cypher transaction succeeds.
- **FR-4**: A CLI entry point `python scripts/ingest_sample.py --limit N --source courtlistener` orchestrates fetch → extract → commit for `N` opinions (default 500).
- **FR-5**: A `Makefile` target `make ingest` invokes the CLI with defaults; the existing `Ingest Sample Data` VS Code task continues to work.
- **FR-6**: `IngestionScout` registers itself in [backend/app/agents/registry.py](../../backend/app/agents/registry.py) under name `IngestionScout`.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: Ingesting 500 opinions completes in ≤ 10 minutes on a developer laptop with local Neo4j + Ollama.
- **NFR-SEC-1**: All HTTP traffic uses `httpx.AsyncClient` with a 30 s timeout and `tenacity` retries (max 3, exponential backoff). No `requests` library. CourtListener API token (when provided) is read from `COURTLISTENER_API_TOKEN` env var; absent token falls back to the public unauthenticated quota.
- **NFR-AUDIT-1**: Every fetch, extraction, and Cypher write is logged through `app.core.provenance` with `agent_version`, `source="courtlistener"`, `source_url`, and `ingest_timestamp` (UTC ISO-8601).
- **NFR-HITL-1**: Any opinion whose `ExtractionResult.confidence < 0.7` is **not** committed to Neo4j; instead it is written to a `pending_review` Postgres table (or, if Postgres is not available, a JSONL file at `backend/var/pending_review/<date>.jsonl`) and the run summary reports the count.
- **NFR-IDEMPOTENT-1**: Re-running ingestion with the same opinion IDs is a no-op (Cypher `MERGE` on `Case {id}`); no duplicate nodes or edges are created.

## 7. Data Model Impact

New / updated Neo4j shapes (will be reflected in `docs/data-model.md` once that file is created by this spec's plan):

- `(:Case {id, title, court, decided_at, source, source_url, ingest_timestamp, agent_version, confidence})`
- `(:Citation {text, normalized})` — created lazily; reused via `MERGE`.
- `(c1:Case)-[:CITES {confidence, ingest_timestamp}]->(c2:Case)` when both endpoints exist.
- `(:Case)-[:HAS_CITATION]->(:Citation)` for every extracted citation, even when the cited case is not yet in the graph.

Postgres: optional `pending_review` table with columns `id, source, payload jsonb, confidence, created_at`.

## 8. API Surface

No new public HTTP routes in this spec. Ingestion is CLI-driven. The existing `/api/health` route should report the latest ingest timestamp from Neo4j (`AC-4`).

## 9. Agent / Crew Impact

- **New runtime agent**: `IngestionScout` (replaces the stub row in [docs/agent-roles.md](../../docs/agent-roles.md)).
- No changes to `LegalAnalyst` or `PrecedentHunter`, but they will start returning non-empty results once data is present.
- Establishes the pattern for future ingestion crews (CAP, legislation.gov.uk).

## 10. Acceptance Criteria

- **AC-1**: Running `make ingest` against a fresh `make dev` stack populates Neo4j with ≥ 450 `Case` nodes (allowing for low-confidence rejects), each carrying all five provenance fields from NFR-AUDIT-1.
- **AC-2**: Re-running `make ingest` immediately after produces zero new nodes and zero new edges (`MERGE` idempotency, NFR-IDEMPOTENT-1).
- **AC-3**: An integration test commits a known fixture opinion and asserts both the `Case` node and at least one `CITES` edge exist.
- **AC-4**: `GET /api/health` returns a `last_ingest_at` ISO-8601 timestamp populated by the most recent successful run; absent any ingest, returns `null`.
- **AC-5**: A unit test seeds an opinion whose extraction confidence is forced below 0.7 and asserts it lands in `pending_review` and **not** in Neo4j (NFR-HITL-1).

## 11. LegalBench Impact

- Tasks affected: none directly (ingestion is data plumbing, not reasoning).
- Expected delta: 0 pp. After this spec lands, a follow-up spec will establish the LegalBench baseline now that `PrecedentHunter` has data.

## 12. Risks & Open Questions

- **R-1**: CourtListener unauthenticated rate limits (~5,000/day) may throttle CI integration tests. Mitigation: cassette-based replay in tests via `respx`; only the `make ingest` target hits the network.
- **R-2**: Eyecite + Blackstone install size and spaCy model download bloat the Docker image. Mitigation: install in the backend image only, document the one-time `python -m spacy download en_core_web_sm` step in plan.md.

## 13. Out of Scope / Follow-ups

- Bulk paginated, resumable ingest (>500 opinions).
- A `pending_review` UI in the frontend.
- Linking Citations to external authorities (USC, CFR) — separate spec.
- LegalBench baseline establishment (separate spec, depends on this one).
