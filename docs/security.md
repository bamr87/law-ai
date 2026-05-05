# Security Model

> Closes [BL-20260430-10](../BACKLOG.md) and [BL-20260503-16](../BACKLOG.md). Operator-facing manual for the API-token model that gates `/api/agents/*`, `/api/analysis`, `/api/graph/*`, and `/api/lsat/*`. Source of truth: [docs/constitution.md](constitution.md) §3 and §8.

## Threat model summary

LawGraph is local-first by default ([docs/constitution.md](constitution.md) §1). The threat model assumes:

1. **Trusted LAN, untrusted internet.** A self-hosted instance may be exposed beyond `localhost`; therefore every gated route must require an API token and reject anonymous traffic when `ENVIRONMENT != "development"`.
2. **No multi-tenant isolation yet.** Tokens are scope-gated, not user-gated. Per-user roles and JWT/OAuth are tracked in [BL-20260503-13](../BACKLOG.md).
3. **Provenance is not optional.** Every gated request is auditable via the `audit.AuditEvent` log and Phoenix traces.
4. **Default-open posture in development.** When `AGENT_API_KEY` is unset and `ENVIRONMENT == "development"`, routes accept unauthenticated requests so `make dev` works out of the box. [BL-20260430-12](../BACKLOG.md) tracks hardening this in production.

## Authentication

- **Header**: `X-API-Key: <token>` on every gated request.
- **Comparison**: `secrets.compare_digest` (constant-time) — see [backend/lawgraph/core/auth.py](../backend/lawgraph/core/auth.py).
- **Storage**: Tokens are persisted in the `core.ApiToken` Django model. Plain-text tokens are returned **only** at creation time; the database stores a SHA-256 `key_hash` for lookup.
- **Frontend**: A single `NEXT_PUBLIC_AGENT_API_KEY` is injected by `frontend/lib/api.ts::apiFetch`. [BL-20260430-07](../BACKLOG.md) tracks moving this to a server-side proxy so it never reaches the browser bundle.

## Scope matrix

`HasScope` (DRF permission) maps an API token to one or more scopes. Each gated route declares the scope it requires.

| Route prefix         | Required scope     | Per-route override env       | Falls back to    | Notes |
|----------------------|--------------------|------------------------------|------------------|-------|
| `/api/agents/*`      | `agents:read`      | `AGENT_API_KEY`              | none             | Spec 008. Includes WS handshakes for `/ws/agents/{run_id}`. |
| `/api/analysis`      | `analysis:invoke`  | `ANALYSIS_API_KEY`           | `AGENT_API_KEY`  | Spec 009. POST only; rate-limit candidate ([BL-20260503-12](../BACKLOG.md)). |
| `/api/graph/*`       | `graph:read`       | `GRAPH_API_KEY`              | `AGENT_API_KEY`  | Spec 009. Read-only neighborhood/path queries. |
| `/api/lsat/*`        | `lsat:invoke`      | `LSAT_API_KEY`               | `AGENT_API_KEY`  | Spec 009. Includes the tutor SSE endpoint when shipped ([BL-20260503-03](../BACKLOG.md)). |
| `/health`            | _(unauth)_         | —                            | —                | Always public, no token required. |

The fallback chain (`<ROUTER>_API_KEY` → `AGENT_API_KEY`) is implemented by `make_api_key_dep(*setting_names)` in `lawgraph.core.auth` and exists so single-key deployments stay simple while multi-tenant operators can rotate per-router. Closes [BL-20260430-13](../BACKLOG.md).

## Token lifecycle

### Issue / seed

```bash
cd backend
python manage.py seed_api_keys --label admin --scopes agents:read,analysis:invoke,graph:read,lsat:invoke
# prints the plain-text token ONCE — copy into your secrets manager / .env
```

The command is idempotent on `label`: re-running with the same label rotates the token and prints the new value (the previous hash is left in the table with `revoked_at` set so audit history survives).

Bulk seed for greenfield environments:

```bash
python manage.py seed_api_keys --from-env
```

…reads `AGENT_API_KEY`, `ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY` from the environment and seeds matching rows. Safe to re-run.

### Rotate

1. Issue a new token with the same scopes (`seed_api_keys --label <label> --rotate`).
2. Roll the new token to clients (env var update + `docker compose restart backend frontend`).
3. Verify the audit log shows new requests under the new `key_hash`.
4. Run `python manage.py revoke_api_key --label <label> --older-than 24h` (planned — see [BL-20260503-13](../BACKLOG.md) follow-up).

### Revoke

```bash
python manage.py revoke_api_key --label <label>
```

Sets `revoked_at = now()`. Authentication immediately rejects the token; existing WebSocket connections are closed by the next ping.

## Auditability

Every authenticated request emits an `audit.AuditEvent` row with:

- `key_hash` — never the plain token.
- `route`, `method`, `status_code`.
- `trace_id` — joins to Phoenix spans (see [docs/local-ai.md](local-ai.md)).
- `actor_label` — the `ApiToken.label` (e.g. `admin`, `frontend`, `ci`).

Operators can query recent activity via the Django admin (`/admin/audit/auditevent/`) or directly:

```sql
SELECT route, count(*), max(created_at) AS last_seen
FROM audit_auditevent
WHERE created_at > now() - interval '7 days'
GROUP BY route
ORDER BY last_seen DESC;
```

## Hardening checklist (production)

- [ ] `ENVIRONMENT=production` set; `DJANGO_SETTINGS_MODULE=lawgraph.settings.prod`.
- [ ] `AGENT_API_KEY` (and any per-router keys) set via secrets manager, not committed `.env`.
- [ ] `seed_api_keys --from-env` run once at boot.
- [ ] HTTPS terminator in front of daphne (Caddy / Traefik / nginx).
- [ ] Per-token rate limiting enabled ([BL-20260503-12](../BACKLOG.md) — pending).
- [ ] Phoenix collector reachable at `PHOENIX_COLLECTOR_ENDPOINT` for trace audit.
- [ ] `python manage.py check --deploy` exits 0.

## Related docs

- [docs/constitution.md](constitution.md) §3 (gates), §8 (security baselines).
- [docs/architecture.md](architecture.md) — auth layer in the API row of the Component Responsibility table.
- [specs/008-agent-api-auth/](../specs/008-agent-api-auth/) and [specs/009-extend-api-auth/](../specs/009-extend-api-auth/).
