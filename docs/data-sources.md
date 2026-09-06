# Data Sources

Open, machine-readable corpora used by Law AI.

| Source                    | URL                                                              | License             | Auth          | Rate limit            | Status   |
| ------------------------- | ---------------------------------------------------------------- | ------------------- | ------------- | --------------------- | -------- |
| **CourtListener**         | https://www.courtlistener.com/api/rest/v3                        | Public domain (US)  | API token (optional, higher quota) | ~5000 req/hr/token | **Active** (spec 001) |
| **Colorado Revised Statutes** | https://law.justia.com/codes/colorado/2024/title-N/          | Underlying CRS text: public domain (US gov work). Justia commentary: CC-BY 4.0. | None | Be polite — ≤ 1 req/sec | **Active** (spec 016) |
| Caselaw Access Project    | https://case.law / https://static.case.law                       | Public domain / CC0 metadata | None (bulk) | None — static bulk downloads | Planned  |
| GovInfo (federal regs)    | https://api.govinfo.gov                                          | Public domain (US)  | API key       | 1000 req/hr           | Planned  |
| eCFR (current CFR text)   | https://www.ecfr.gov/developers/documentation/api/v1             | Public domain (US)  | None          | Be polite             | Planned  |
| U.S. Code (OLRC)          | https://uscode.house.gov/download/download.shtml                 | Public domain (US)  | None (bulk XML) | None — bulk releases | Planned  |
| RECAP archive (dockets)   | https://www.courtlistener.com/api/rest/v3 (recap endpoints)      | Public domain (US)  | API token     | shared with CourtListener | Planned  |

> **CAP note (2024 update).** The 500-cases/day quota above described CAP's pre-2024
> research-access terms. In March 2024 the Caselaw Access Project released the full
> ~6.9M-case corpus as unrestricted bulk data (static downloads; also merged into
> CourtListener's collection). A jurisdiction-scoped bulk import is therefore viable
> and is tracked in BACKLOG. Per constitution §5/§12-I2, each new source adapter
> still requires its own `/specify` cycle with HITL quarantine — this table records
> candidates, not authorization.

## CourtListener

- Endpoint: `GET /opinions/{id}/` and `GET /opinions/?cursor=...`
- Client: [backend/law_ai/ingestionapp/services/courtlistener.py](../backend/law_ai/ingestionapp/services/courtlistener.py)
- Configuration:
  - `COURTLISTENER_API_KEY` — env var defined in [backend/law_ai/settings/base.py](../backend/law_ai/settings/base.py), read via `law_ai.core.settings_proxy`. Optional but recommended.
- Retry policy: 3 attempts, exponential backoff on 429 / 5xx / transport errors (`tenacity.AsyncRetrying`).
- Sample command: `make ingest` (defaults to `--limit 500 --source courtlistener`).

## Colorado Revised Statutes (CRS)

- Endpoint pattern: `GET https://law.justia.com/codes/colorado/<year>/title-<N>/` (one HTML page per CRS title, e.g. Title 18 — Criminal Code).
- Client: [backend/law_ai/ingestionapp/services/colorado_statutes.py](../backend/law_ai/ingestionapp/services/colorado_statutes.py)
- Parser: deterministic `parse_title_html(title_id, html)` in the same module — bs4 + a small regex pack; fixture-tested at [backend/tests/ingestion/test_colorado_statutes_parser.py](../backend/tests/ingestion/test_colorado_statutes_parser.py).
- Crew: [`StatuteScout`](../backend/law_ai/ingestionapp/services/statute_scout.py) — same `extract` / `run_and_commit` shape as `IngestionScout`. Low-confidence sections quarantine to `PendingReview` with `kind="statute_section"`.
- Configuration:
  - `COLORADO_STATUTES_BASE_URL` — env var override (e.g. for a local mirror in tests). Defaults to `https://law.justia.com/codes/colorado/2024`.
- Retry policy: 3 attempts, exponential backoff on 429 / 5xx / transport errors (`tenacity.AsyncRetrying`).
- License posture:
  - **Underlying CRS text** is uncopyrightable U.S. state-government work; redistributable.
  - **Justia commentary / page chrome** is CC-BY 4.0; we do not store commentary, only the section body text we extract.
  - Cached source HTML is provenance-tracked (`source_url` on every node). Any future public dataset export will exclude raw cached HTML.
- Sample command (Docker-first — see [CLAUDE.md](../CLAUDE.md); never run this bare on the host):
  ```bash
  docker compose run --rm backend python scripts/ingest_sample.py --source colorado_statutes --titles 18 --dry-run
  docker compose run --rm backend python scripts/ingest_sample.py --source colorado_statutes --titles 18,42  # commits to Neo4j
  ```
- v1 scope: Colorado Title 18 (Criminal Code), Article 3 (Offenses Against the Person). Additional titles are a one-line `--titles` change.
- PDF fallback (BL-20260509-06): set `COLORADO_STATUTES_PDF_BASE_URL` (a directory of `title-<N>.pdf`, or a template containing `{title}`) and `ColoradoStatutesClient.fetch_title_document` falls back to `parse_title_pdf` when the HTML fetch fails. Local publications can be parsed offline with `python scripts/ingest_sample.py --source colorado_statutes --titles 18 --pdf-dir /path/to/pdfs`. PDF-derived sections are penalised by `PDF_CONFIDENCE_PENALTY` so they always land in the HITL queue — CRS PDFs are column-laid-out and naive text extraction interleaves columns. A whole penalised import can be cleared in one scoped decision once a reviewer has satisfied themselves about the title (BL-20260905-98): `python manage.py review_queue approve-all --id-prefix us-co/crs/18- --reviewer-user alice --note "spot-checked the import"`. The verb refuses to run without a `--source` / `--kind` / `--id-prefix` scope, and `--reviewer-user` records the decision against a real Django account (BL-20260906-20).
- Live-network drift smoke (BL-20260511-07): `make test-live-network` runs [backend/tests/ingestion/test_colorado_statutes_live.py](../backend/tests/ingestion/test_colorado_statutes_live.py) — one real Justia fetch, re-run through the parser, gated behind `LIVE_NETWORK=1` and the `network` marker. It runs nightly with `continue-on-error` and never in per-PR CI.
- Follow-ups: none outstanding — Denver Municipal Code (`BL-20260509-05`) is below, and `:CITES_STATUTE` edges from existing case law (`BL-20260509-07`) shipped; see [data-model.md](data-model.md#cross-corpus-reasoning-spec-015).

## Denver Revised Municipal Code (DRMC)

Deferred out of spec 016 as "spec 016.b" and delivered under `BL-20260509-05`. It is the first municipal corpus in the graph and the first producer of the `Ordinance` / `OrdinanceSection` labels spec 015 declared.

- Client: [backend/law_ai/ingestionapp/services/denver_municipal_code.py](../backend/law_ai/ingestionapp/services/denver_municipal_code.py) — same async httpx + tenacity shape as the CRS client.
- Parser: deterministic `parse_chapter_html(chapter, html)` in the same module (lxml + a small regex pack), fixture-tested at [backend/tests/ingestion/test_denver_municipal_code_parser.py](../backend/tests/ingestion/test_denver_municipal_code_parser.py).
- Crew: [`OrdinanceScout`](../backend/law_ai/ingestionapp/services/ordinance_scout.py) — `extract` / `run_and_commit` / `commit_section`, quarantining to `PendingReview` with `kind="ordinance_section"`.
- Graph writer: [`ordinance_queries.py`](../backend/law_ai/core/neo4j/ordinance_queries.py). The tree is `Jurisdiction ← Ordinance ← OrdinanceSection`; there is no `Code` node between them because a municipal code has no title layer.
- Ids and citations: `us-co-denver/dmc/chapter-38` for a chapter, `us-co-denver/dmc/38-31` for a section, cited `D.R.M.C. § 38-31`.
- Configuration:
  - `DENVER_MUNICIPAL_CODE_BASE_URL` — override for a mirror you are permitted to crawl. Defaults to the Municode URL, which the shipped workflow does not fetch.

### License and access posture

**The default workflow is offline, and that is deliberate.** The DRMC text itself is a municipal government work and is not copyrightable, but the hosting is not open: [library.municode.com](https://library.municode.com/co/denver/codes/code_of_ordinances) renders the code through a JavaScript client under terms of use that prohibit systematic downloading, and what an HTTP client receives is not what a browser renders. So:

- **Fetching is opt-in.** `--chapter-dir` parses local HTML and never constructs a client (there is a test that asserts exactly that). Point `DENVER_MUNICIPAL_CODE_BASE_URL` at a source you have permission to crawl before using the network path.
- **Every section is quarantined.** `DenverMunicipalCodeAdapter.requires_human_approval = True` and `OrdinanceScout.requires_human_approval = True`, so a person reads every ordinance before it reaches the graph (constitution §5) — regardless of the parser's confidence score. Approved rows commit through `approval._commit_by_kind` → `OrdinanceScout.commit_section`, the same audited path statutes use.
- **Redistribution: false.** Cached source HTML is provenance-tracked (`source_url` on every node) and excluded from any public dataset export. The checked-in test fixture is hand-reduced placeholder prose that pins the markup contract, not a copy of the code.
- Rate limit: `0.25 rps` — half the Justia adapter's, because this is not a host we have permission to crawl at volume.

- Sample command (Docker-first — see [CLAUDE.md](../CLAUDE.md); never run this bare on the host):
  ```bash
  docker compose run --rm backend python scripts/ingest_sample.py --source denver_municipal_code --chapters 38 --chapter-dir backend/tests/ingestion/fixtures/denver --dry-run
  # commit mode: sections go to the HITL queue, not the graph — "committed=0" is correct
  docker compose run --rm backend python scripts/ingest_sample.py --source denver_municipal_code --chapters 38 --chapter-dir /path/to/html
  # every chapter the local directory holds, no hand-typed list (BL-20260906-06)
  docker compose run --rm backend python scripts/ingest_sample.py --source denver_municipal_code --chapters all --chapter-dir /path/to/html --dry-run
  ```
- Chapter discovery (`BL-20260906-06`): `--chapters all` reads the chapter list instead of taking a hand-typed one — from the `chapter-*.html` files in `--chapter-dir` offline, or from the code's table of contents (`DenverMunicipalCodeClient.list_chapters` → `parse_chapter_index`) when fetching is enabled. A page with no chapter links yields an empty list rather than a guessed range.
- Still out of scope: the code's article/division layer (`Ordinance` remains one flat node per chapter, so an article is neither a node nor a property yet) and `CITES`/`INTERPRETS` edges between ordinances and the statutes they implement.

## Autonomy source adapters

The autonomy orchestrator (`make autonomy-run KIND=… SOURCE=…`) does not call the `services/` clients above directly — it goes through a thin adapter layer at [backend/law_ai/ingestionapp/sources/](../backend/law_ai/ingestionapp/sources/) (`SourceAdapter`, `RawDoc`, `SOURCE_REGISTRY`, spec 018), which wraps `services/courtlistener.py`, `services/colorado_statutes.py` and `services/denver_municipal_code.py` for scheduled/autonomous runs. The `services/` clients documented above remain the real HTTP clients; the adapter layer only normalizes their output for the autonomy loop.

Each adapter declares `name`, `jurisdiction`, `license`, `requires_human_approval`, and `rate_limit_rps`. Setting `requires_human_approval=True` makes `TopicFrontier` dispatch with `force_quarantine=True`, so every document from that source is held in `PendingReview` regardless of confidence and can never be auto-committed — the full contract is in [docs/architecture.md](architecture.md#source-adapter-contract).
