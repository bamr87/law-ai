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
- Follow-ups: live-network nightly smoke (BL-20260509-04), Denver Municipal Code (BL-20260509-05), PDF fallback (BL-20260509-06), `:CITES_STATUTE` edges from existing case law (BL-20260509-07).

## Autonomy source adapters

The autonomy orchestrator (`make autonomy-run KIND=… SOURCE=…`) does not call the `services/` clients above directly — it goes through a thin adapter layer at [backend/law_ai/ingestionapp/sources/](../backend/law_ai/ingestionapp/sources/) (`SourceAdapter`, `RawDoc`, `SOURCE_REGISTRY`, spec 018), which wraps `services/courtlistener.py` and `services/colorado_statutes.py` for scheduled/autonomous runs. The `services/` clients documented above remain the real HTTP clients; the adapter layer only normalizes their output for the autonomy loop.
