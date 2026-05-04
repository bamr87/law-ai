# Data Sources

Open, machine-readable corpora used by LexGraph AI.

| Source              | URL                                                    | License             | Auth          | Rate limit            | Status   |
| ------------------- | ------------------------------------------------------ | ------------------- | ------------- | --------------------- | -------- |
| **CourtListener**   | https://www.courtlistener.com/api/rest/v3              | Public domain (US)  | API token (optional, higher quota) | ~5000 req/hr/token | **Active** (spec 001) |
| Caselaw Access Project | https://case.law                                    | CC BY-NC            | API token     | 500 cases/day (free)  | Planned  |
| GovInfo (federal regs) | https://api.govinfo.gov                             | Public domain (US)  | API key       | 1000 req/hr           | Planned  |

## CourtListener

- Endpoint: `GET /opinions/{id}/` and `GET /opinions/?cursor=...`
- Client: [backend/app/ingestion/courtlistener.py](../backend/app/ingestion/courtlistener.py)
- Configuration:
  - `COURTLISTENER_API_KEY` — env var read by `core.config.settings`. Optional but recommended.
- Retry policy: 3 attempts, exponential backoff on 429 / 5xx / transport errors (`tenacity.AsyncRetrying`).
- Sample command: `make ingest` (defaults to `--limit 500 --source courtlistener`).
