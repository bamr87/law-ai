# Tasks: Colorado Statute Ingestion

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces coverage.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Pydantic schemas for statute extraction

- **Refs**: FR-2, FR-3, NFR-AUDIT-1, NFR-OSS-1, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/schemas/statute_extraction.py` (new)
  - `backend/lawgraph/core/schemas/__init__.py` (re-export)
- **Steps**:
  1. Add `StatuteSectionPayload` (id, citation, heading, text, optional `effective_from`, per-section `confidence`) and `StatuteExtraction` (jurisdiction code/name/level, code id+title, statute id+title, sections list, top-level provenance).
  2. Re-export both from `core/schemas/__init__.py`.
- **Verify**: `cd backend && pytest tests/ingestion/test_colorado_statutes_parser.py -q`.

## T-002 — Justia HTML client + deterministic parser

- **Refs**: FR-1, FR-2, NFR-PERF-1, NFR-SEC-1, NFR-OSS-1, AC-1, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/ingestionapp/services/colorado_statutes.py` (new — client + parser)
  - `backend/tests/ingestion/fixtures/co/title_18_article_3.html` (new — checked-in fixture)
- **Steps**:
  1. Implement `ColoradoStatutesClient` with the same async/`tenacity`/provenance shape as `CourtListenerClient`. Base URL constant overridable via `COLORADO_STATUTES_BASE_URL`.
  2. Implement `parse_title_html(title_id, html) -> StatuteExtraction`. Strip `<script>`/`<style>` before extracting `text`.
  3. Build the fixture: a small (~5 sections from Article 3) snippet representative of the real Justia page structure, sufficient to exercise the parser.
- **Verify**: `cd backend && pytest tests/ingestion/test_colorado_statutes_parser.py -q`.

## T-003 — `StatuteScout` ingestion crew

- **Refs**: FR-3, FR-4, FR-5, NFR-AUDIT-1, NFR-IDEMPOTENT-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/ingestionapp/services/statute_scout.py` (new)
- **Steps**:
  1. `StatuteScout(name="StatuteScout", agent_version="0.1.0", requires_human_approval=False, CONFIDENCE_THRESHOLD=0.7)`.
  2. `extract({"title_id": "...", "html": "..."}) -> StatuteExtraction` calls the parser and stamps provenance.
  3. `async run_and_commit(payload) -> dict`: separates sections into `committed` (≥0.7) and `pending` (<0.7); commits via `commit_statute_extraction`; quarantines via Celery task with `kind="statute_section"`; falls back to JSONL on failure; logs through `core.provenance`.
- **Verify**: `cd backend && pytest tests/ingestion/test_statute_scout.py -q`.

## T-004 — Cypher MERGE for statute tree

- **Refs**: FR-5, NFR-AUDIT-1, NFR-SEC-1, NFR-IDEMPOTENT-1, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/neo4j/statute_queries.py` (new)
- **Steps**:
  1. Constants: `MERGE_JURISDICTION_CYPHER`, `MERGE_CODE_CYPHER`, `MERGE_STATUTE_CYPHER`, `MERGE_STATUTE_SECTION_CYPHER`, `MERGE_PART_OF_*`, `MERGE_IN_JURISDICTION_*`.
  2. `async commit_statute_extraction(session, extraction) -> int` returns edge count; uses parameter binding only.
- **Verify**: covered by `test_statute_scout.py` via `AsyncMock` session call assertions.

## T-005 — Quarantine task carries `kind`

- **Refs**: FR-6, AC-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/ingestionapp/tasks.py` (extend)
- **Steps**:
  1. `quarantine_extraction(payload)` reads `payload.get("kind", "case")` and writes it to `PendingReview.kind`.
  2. Audit event payload includes the kind.
- **Verify**: `cd backend && pytest tests/ingestion/test_quarantine_task.py -q`.

## T-006 — CLI `--source colorado_statutes`

- **Refs**: FR-7, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/scripts/ingest_sample.py` (extend)
- **Steps**:
  1. Add `colorado_statutes` to `--source` choices and a comma-separated `--titles` arg.
  2. Dispatch to a new `_run_colorado(args)` that uses `ColoradoStatutesClient` + `StatuteScout`.
  3. Keep CourtListener path untouched.
- **Verify**: `cd backend && pytest tests/ingestion/test_ingest_cli_colorado.py -q`.

## T-007 — Documentation

- **Refs**: FR-8, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/data-sources.md` (extend)
- **Steps**:
  1. Add a "Colorado Revised Statutes" row to the table (status: Active).
  2. Add a detail block: source URL pattern, license posture, env var, retry policy, sample CLI command.
- **Verify**: `cd /Users/bamr87/law-ai && python3 -m pytest tests/test_docs.py -q`.

## T-008 — Tests + spec validator

- **Refs**: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/ingestion/test_colorado_statutes_parser.py` (new)
  - `backend/tests/ingestion/test_statute_scout.py` (new)
  - `backend/tests/ingestion/test_quarantine_task.py` (extend)
  - `backend/tests/ingestion/test_ingest_cli_colorado.py` (new)
- **Steps**:
  1. Author tests per the strategy in [plan.md](plan.md) §7.
  2. Run `python scripts/spec_validator.py` and `python scripts/backlog_lint.py`.
- **Verify**: all of the above pytest commands green; spec validator reports `PASS specs/016-ingest-colorado-statutes`.

---

## Follow-ups Discovered

> Mirror each entry into [BACKLOG.md](../../BACKLOG.md) per [docs/constitution.md](../../docs/constitution.md) §11.

- **BL-20260509-04** — *test-gap, med* — Live-network nightly smoke test that fetches one real Justia CRS title and re-runs the parser to detect upstream HTML drift. _Surfaced in:_ specs/016-ingest-colorado-statutes.
- **BL-20260509-05** — *feature, med* — Denver Municipal Code ingestion (`Ordinance` / `OrdinanceSection` writes) — spec 016.b. Out of scope for the Colorado-statutes MVP. _Surfaced in:_ specs/016-ingest-colorado-statutes.
- **BL-20260509-06** — *feature, low* — PDF parsing path for LexisNexis CRS publications as a fallback when the HTML source is unavailable. Requires `pypdf` (already in stack). _Surfaced in:_ specs/016-ingest-colorado-statutes.
- **BL-20260509-07** — *feature, med* — Citation-resolver pass that creates `(:Case)-[:CITES_STATUTE]->(:StatuteSection)` edges from existing opinion text once the CRS corpus is loaded. Likely lives in a 002.b spec or rolls into spec 018. _Surfaced in:_ specs/016-ingest-colorado-statutes.
