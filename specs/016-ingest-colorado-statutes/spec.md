# Spec: Colorado Statute Ingestion (CRS Title 18, MVP slice)

- **ID**: 016-ingest-colorado-statutes
- **Status**: in-progress
- **Owner**: @copilot
- **Created**: 2026-05-09
- **Roadmap Epic**: Legal corpus + Hybrid GraphRAG foundation (umbrella plan in session memory `/memories/session/plan.md`).
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §1 (open-source / privacy-first), §4 (provenance), §11 (continuous-evolution), and the agent-runtime rules in [.github/instructions/agents.instructions.md](../../.github/instructions/agents.instructions.md).

## 1. Problem & Motivation

Spec 015 declared the `Statute` / `StatuteSection` / `Code` / `Jurisdiction` schema, but nothing writes to it. Every reasoning path in LawGraph still operates on opinions only. Without a real statutory corpus we cannot exercise the spec-015 schema, validate the spec-018 hybrid retriever against statutory queries, or measure spec-019 derived-document feedback against primary law. This spec lands the first non-opinion ingestion source: a **MVP slice of Colorado Revised Statutes (CRS) Title 18 (Criminal Code)** parsed from clean public HTML, written through the same `IngestionScout`-shaped scout/quarantine/commit pipeline that already serves CourtListener.

## 2. Goals

- **G1**: Parse a CRS Title 18 HTML page into a typed `StatuteExtraction(statute, sections=[...])` payload using only stdlib + already-installed deps (`beautifulsoup4`, `httpx`, `tenacity`).
- **G2**: Provide a `ColoradoStatutesClient` HTTP client mirroring `CourtListenerClient` (async, retried, provenance-logged) so future titles can be ingested with `--titles 18,42`.
- **G3**: Provide a `StatuteScout` ingestion crew with the same `extract` / `run_and_commit` shape as `IngestionScout`, routing low-confidence extractions through the spec-015 `kind="statute_section"` quarantine.
- **G4**: Add Cypher MERGE helpers for `Jurisdiction`, `Code`, `Statute`, `StatuteSection`, `:PART_OF`, `:IN_JURISDICTION` so the scout can persist a section tree idempotently.
- **G5**: Extend `backend/scripts/ingest_sample.py` with `--source colorado_statutes --titles 18` and update [docs/data-sources.md](../../docs/data-sources.md) with the CRS source row + license note.

## 3. Non-Goals

- **NG1**: PDF parsing (LexisNexis CRS publications). Offline HTML fixtures only for v1; PDF support is a follow-up.
- **NG2**: Denver Municipal Code (`Ordinance` / `OrdinanceSection`). Filed as Phase B sub-follow-up; spec 016.b will follow once Title 18 is green.
- **NG3**: `:CITES_STATUTE` / `:INTERPRETS` edges from existing `Case` nodes to new `StatuteSection` nodes — those depend on a separate citation-resolver pass and belong to spec 002.b or spec 018.
- **NG4**: Embeddings on the new sections — that is spec 017.
- **NG5**: Live-network integration tests against `law.justia.com`. All HTTP is mocked via `respx` cassettes; a docker-backed live-fetch test is a Phase B follow-up.
- **NG6**: A real Cypher migration runner — still a follow-up from spec 015 (BL-20260509-02).

## 4. User Stories

- As an **ingestion engineer**, I want `python scripts/ingest_sample.py --source colorado_statutes --titles 18 --dry-run` to walk a fixture HTML page and report `committed=N pending=M` so I can validate the parser without touching Neo4j.
- As an **operator**, I want low-confidence statute sections to land in the same `pending_review` table as low-confidence cases (with `kind="statute_section"`), so I can triage everything in one Django admin pane.
- As a **graph engineer**, I want `(:StatuteSection)-[:PART_OF]->(:Statute)-[:PART_OF]->(:Code)-[:IN_JURISDICTION]->(:Jurisdiction)` to MERGE idempotently from the same payload, so re-running ingestion does not duplicate the tree.

## 5. Functional Requirements

- **FR-1**: `backend/lawgraph/ingestionapp/services/colorado_statutes.py` provides `ColoradoStatutesClient` (async, `httpx`-backed, `tenacity`-retried on 429/5xx/transport, provenance-logged via `core.provenance`) with `async fetch_title(title: str) -> str` returning raw HTML and `async iter_titles(titles: Iterable[str]) -> AsyncIterator[tuple[str, str]]` yielding `(title_id, html)` pairs.
- **FR-2**: A pure parser `parse_title_html(title_id: str, html: str) -> StatuteExtraction` (stdlib + bs4) extracts: code metadata (`us-co/crs`, "Colorado Revised Statutes"), statute metadata (`us-co/crs/title-18`, title text), and a list of `StatuteSectionPayload` rows with `id`, `citation` (e.g. `C.R.S. § 18-3-102`), `heading`, `text`, optional `effective_from`. Parser is deterministic and unit-testable on canned fixtures.
- **FR-3**: `backend/lawgraph/ingestionapp/services/statute_scout.py` provides `StatuteScout` with `extract(payload: dict) -> StatuteExtraction` and `async run_and_commit(payload: dict) -> dict`. `agent_version = "0.1.0"`, `requires_human_approval = False`, `CONFIDENCE_THRESHOLD = 0.7`. The summary dict has shape `{"title_id", "committed", "pending", "sections_total", "edges"}`.
- **FR-4**: A new pure scoring helper `_score_section(text: str, citation: str | None) -> float` returns 0..1; sections below 0.7 quarantine, ≥ 0.7 commit. Statute-tree nodes (Jurisdiction / Code / Statute) always commit when their parent title commits at all (they are administrative metadata, not extracted content).
- **FR-5**: `backend/lawgraph/core/neo4j/statute_queries.py` provides `async commit_statute_extraction(session, extraction) -> int` returning the number of `:PART_OF` + `:IN_JURISDICTION` edges created. All writes use `MERGE` keyed on the spec-015 unique-constraint properties so re-running is a no-op.
- **FR-6**: `quarantine_extraction` Celery task ([backend/lawgraph/ingestionapp/tasks.py](../../backend/lawgraph/ingestionapp/tasks.py)) honors `payload["kind"]` (defaulting to `"case"` when absent) and persists it to the spec-015 `PendingReview.kind` column. Backwards-compatible with existing CourtListener call sites.
- **FR-7**: `backend/scripts/ingest_sample.py` accepts `--source colorado_statutes` and `--titles 18,42` (comma-separated). When `--source colorado_statutes` is selected, `--limit` becomes the per-title section cap. Default still routes to CourtListener.
- **FR-8**: [docs/data-sources.md](../../docs/data-sources.md) gains a "Colorado Revised Statutes" row in the table and a detail block with: source URL pattern, license posture, env var (`COLORADO_STATUTES_BASE_URL` for override), retry policy, and sample CLI command. License note states underlying CRS text is uncopyrightable government work; cached HTML provenance is recorded per node.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every `StatuteSection` and `Statute` node persisted carries the constitution §4 provenance fields (`source="colorado_statutes"`, `source_url`, `confidence`, `ingest_timestamp`, `agent_version`). Every parser/scout call logs via `core.provenance.log_agent_call` with the section count.
- **NFR-IDEMPOTENT-1**: Re-running `ingest_sample.py --source colorado_statutes --titles 18` against the same fixture creates **0 duplicate** Statute / StatuteSection / PART_OF / IN_JURISDICTION rows on a second pass. Verified by integration-style unit test that runs commit twice against a fake Neo4j session and asserts identical MERGE call counts.
- **NFR-SEC-1**: All Cypher uses parameter binding; no f-string interpolation of payload data into queries (OWASP A03). The HTML parser strips `<script>` / `<style>` tags before storing `text` to avoid downstream injection in the future Analysis Studio HTML rendering.
- **NFR-OSS-1**: No new third-party dependencies. `httpx`, `tenacity`, `beautifulsoup4`, `pytest-asyncio`, `respx` are already in [backend/pyproject.toml](../../backend/pyproject.toml).
- **NFR-PERF-1**: Parsing one CRS title (≤ 100 sections) completes in < 500 ms on the test fixture (parser is regex+bs4, no LLM call).

## 7. Data Model Impact

No schema changes — this spec only **writes** to labels declared by spec 015. New nodes/edges produced:

| Action  | Shape                                                                          |
| ------- | ------------------------------------------------------------------------------ |
| MERGE   | `(:Jurisdiction {code:'us-co'})`                                               |
| MERGE   | `(:Code {id:'us-co/crs'})`                                                     |
| MERGE   | `(:Statute {id:'us-co/crs/title-18'})`                                         |
| MERGE   | `(:StatuteSection {id:'us-co/crs/18-3-102'})` × N                              |
| MERGE   | `(:StatuteSection)-[:PART_OF]->(:Statute)`                                     |
| MERGE   | `(:Statute)-[:PART_OF]->(:Code)`                                               |
| MERGE   | `(:Code)-[:IN_JURISDICTION]->(:Jurisdiction)` (and `(:Statute)→(:Jurisdiction)` for fast filter) |

`PendingReview.kind = "statute_section"` for any section below the confidence threshold.

## 8. API Surface

None. CLI only (FR-7). DRF routes to expose statute sections to the frontend are deferred to a follow-up.

## 9. Agent / Crew Impact

- New crew member: `StatuteScout` (parallel to `IngestionScout`). Lives in `backend/lawgraph/ingestionapp/services/statute_scout.py` (consistent with existing `services/scout.py`), but it satisfies the agent-runtime contract from [.github/instructions/agents.instructions.md](../../.github/instructions/agents.instructions.md): typed `extract` / `run_and_commit`, provenance logging, optional HITL via confidence threshold, and `agent_version` string.
- No prompt files (rule-based parser, not LLM-driven). When the LegalAnalyst eventually grounds answers in CRS sections (spec 018), a versioned prompt will land then.

## 10. Acceptance Criteria

- **AC-1**: `pytest backend/tests/ingestion/test_colorado_statutes_parser.py -q` passes — parser turns the fixture HTML into a `StatuteExtraction` with the expected number of sections, citations, and provenance fields.
- **AC-2**: `pytest backend/tests/ingestion/test_statute_scout.py -q` passes — `extract` produces a typed payload, `run_and_commit` against a fake Neo4j session writes the expected MERGE calls, low-confidence sections are routed to the Celery quarantine task with `kind="statute_section"`, and re-running produces no duplicate MERGE invocations (NFR-IDEMPOTENT-1).
- **AC-3**: `pytest backend/tests/ingestion/test_quarantine_task.py -q` passes — the `quarantine_extraction` task persists `payload["kind"]` (when set) to `PendingReview.kind`; default remains `"case"` (FR-6 backwards compat).
- **AC-4**: `python scripts/ingest_sample.py --source colorado_statutes --titles 18 --dry-run` (run against the bundled fixture) prints a non-zero `committed` count and exit 0. Verified by `tests/ingestion/test_ingest_cli_colorado.py`.
- **AC-5**: [docs/data-sources.md](../../docs/data-sources.md) renders a new CRS row + detail block; `tests/test_docs.py` (existing repo-level test) still passes.
- **AC-6**: `python scripts/spec_validator.py` passes for `specs/016-ingest-colorado-statutes/`.

## 11. LegalBench Impact

- Tasks affected: none directly (LegalBench is opinion-centric).
- Expected delta: **0 pp**. Real impact lands when spec 018 grounds answers in CRS sections.

## 12. Risks & Open Questions

- **R-1** (med): Justia HTML structure may change. Mitigation: parser uses generous CSS selectors with fallbacks; all selectors are constants at the top of `colorado_statutes.py` so a future site change is a one-line patch. Live-fetch smoke job is a follow-up.
- **R-2** (low): Postgres `pending_review.kind` was sized at 32 chars (spec 015 FR-6). `statute_section` = 15 chars; safe headroom.
- **OQ-1**: ~~Fetch full Title 18 (~250 sections) or only Article 3 (homicide) for v1?~~ Resolved during /clarify: **Article 3 only** (~25 sections) — small enough for a checked-in fixture, large enough to exercise the full tree.

## 13. Out of Scope / Follow-ups

- PDF parsing for LexisNexis CRS publications.
- Denver Municipal Code (`Ordinance` / `OrdinanceSection`) — spec 016.b.
- Live-network smoke test that fetches `law.justia.com` once per CI nightly.
- `:CITES_STATUTE` / `:INTERPRETS` edges from existing `Case` text — owned by spec 018 (retriever) or a new 002.b citation-resolver pass.
- Frontend: a `/codes/co/crs/title-18` browse view and an API route to back it.
