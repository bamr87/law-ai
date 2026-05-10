# Data Sources

Open, machine-readable corpora used by LawGraph AI.

| Source                    | URL                                                              | License             | Auth          | Rate limit            | Status   |
| ------------------------- | ---------------------------------------------------------------- | ------------------- | ------------- | --------------------- | -------- |
| **CourtListener**         | https://www.courtlistener.com/api/rest/v3                        | Public domain (US)  | API token (optional, higher quota) | ~5000 req/hr/token | **Active** (spec 001) |
| **Colorado Revised Statutes** | https://law.justia.com/codes/colorado/2024/title-N/          | Underlying CRS text: public domain (US gov work). Justia commentary: CC-BY 4.0. | None | Be polite — ≤ 1 req/sec | **Active** (spec 016) |
| Caselaw Access Project    | https://case.law                                                 | CC BY-NC            | API token     | 500 cases/day (free)  | Planned  |
| GovInfo (federal regs)    | https://api.govinfo.gov                                          | Public domain (US)  | API key       | 1000 req/hr           | Planned  |

## CourtListener

- Endpoint: `GET /opinions/{id}/` and `GET /opinions/?cursor=...`
- Client: [backend/lawgraph/ingestionapp/services/courtlistener.py](../backend/lawgraph/ingestionapp/services/courtlistener.py)
- Configuration:
  - `COURTLISTENER_API_KEY` — env var read by `core.config.settings`. Optional but recommended.
- Retry policy: 3 attempts, exponential backoff on 429 / 5xx / transport errors (`tenacity.AsyncRetrying`).
- Sample command: `make ingest` (defaults to `--limit 500 --source courtlistener`).

## Colorado Revised Statutes (CRS)

- Endpoint pattern: `GET https://law.justia.com/codes/colorado/<year>/title-<N>/` (one HTML page per CRS title, e.g. Title 18 — Criminal Code).
- Client: [backend/lawgraph/ingestionapp/services/colorado_statutes.py](../backend/lawgraph/ingestionapp/services/colorado_statutes.py)
- Parser: deterministic `parse_title_html(title_id, html)` in the same module — bs4 + a small regex pack; fixture-tested at [backend/tests/ingestion/test_colorado_statutes_parser.py](../backend/tests/ingestion/test_colorado_statutes_parser.py).
- Crew: [`StatuteScout`](../backend/lawgraph/ingestionapp/services/statute_scout.py) — same `extract` / `run_and_commit` shape as `IngestionScout`. Low-confidence sections quarantine to `PendingReview` with `kind="statute_section"`.
- Configuration:
  - `COLORADO_STATUTES_BASE_URL` — env var override (e.g. for a local mirror in tests). Defaults to `https://law.justia.com/codes/colorado/2024`.
- Retry policy: 3 attempts, exponential backoff on 429 / 5xx / transport errors (`tenacity.AsyncRetrying`).
- License posture:
  - **Underlying CRS text** is uncopyrightable U.S. state-government work; redistributable.
  - **Justia commentary / page chrome** is CC-BY 4.0; we do not store commentary, only the section body text we extract.
  - Cached source HTML is provenance-tracked (`source_url` on every node). Any future public dataset export will exclude raw cached HTML.
- Sample command:
  ```bash
  cd backend
  python scripts/ingest_sample.py --source colorado_statutes --titles 18 --dry-run
  python scripts/ingest_sample.py --source colorado_statutes --titles 18,42  # commits to Neo4j
  ```
- v1 scope: Colorado Title 18 (Criminal Code), Article 3 (Offenses Against the Person). Additional titles are a one-line `--titles` change.
- Follow-ups: live-network nightly smoke (BL-20260509-04), Denver Municipal Code (BL-20260509-05), PDF fallback (BL-20260509-06), `:CITES_STATUTE` edges from existing case law (BL-20260509-07).
