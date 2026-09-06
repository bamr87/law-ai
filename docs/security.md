# Security Model

> Closes [BL-20260430-10](../BACKLOG.md) and [BL-20260503-16](../BACKLOG.md). Operator-facing manual for the API-token model that gates `/api/agents/*`, `/api/analysis`, `/api/graph/*`, and `/api/lsat/*`. Source of truth: [docs/constitution.md](constitution.md) §4 (provenance/audit) and §8 (security baselines).

## Threat model summary

Law AI's product-runtime LLM defaults to Claude over the `LLM_PROVIDER_CHAIN` (local-only is an explicit `LLM_PROVIDER_CHAIN=ollama` pin, required for confidentiality-bound data — [docs/constitution.md](constitution.md) §1), while every other component (databases, graph store, ingestion) stays local-first regardless. The threat model assumes:

1. **Trusted LAN, untrusted internet.** A self-hosted instance may be exposed beyond `localhost`. In practice, `HasScope.has_permission` ([backend/law_ai/core/auth.py](../backend/law_ai/core/auth.py)) opens a route to unauthenticated traffic whenever the route's `*_API_KEY` setting is empty — **regardless of `ENVIRONMENT`**. There is no code path that checks `ENVIRONMENT` before granting this fallback, so a production deployment that forgets to set `AGENT_API_KEY` is silently open on every gated router, not just in dev. [BL-20260430-12](../BACKLOG.md) tracks making `ENVIRONMENT=production` refuse to boot with an unset `AGENT_API_KEY` instead of just leaving the gate open; until that lands, treat "every `*_API_KEY` is set in production" as a hard operational requirement, not a convenience.
2. **No multi-tenant isolation yet.** Tokens are scope-gated, not user-gated. Per-user roles and JWT/OAuth are tracked in [BL-20260503-13](../BACKLOG.md).
3. **Provenance is not optional.** Every request through `ProvenanceMiddleware` and every LLM call through `law_ai.core.llm` is auditable via the `audit.AuditEvent` log (see [Auditability](#auditability)) and, when `PHOENIX_COLLECTOR_ENDPOINT` is configured, Phoenix traces.
4. **Default-open posture whenever a router's key is unset.** `HasScope` grants access when neither an `ApiToken` row nor an env-configured `*_API_KEY` matches the requested scope — this is what lets `make dev` work with zero setup, but it is the *same* code path that makes an unconfigured production deployment open. See item 1.

## Authentication

Two independent mechanisms feed the same `HasScope` check, and it matters which one a request goes through:

- **DB-token path**: `ApiKeyAuthentication` ([core/auth.py](../backend/law_ai/core/auth.py)) reads the `X-API-Key` header, SHA-256-hashes it, and looks up a non-revoked `core.ApiToken` row by `key_hash`. On a match, `HasScope` grants access if the token's `scope` equals the route's scope **or the token's scope is `"agent"`** — an `agent`-scoped `ApiToken` is a master key across every gated router, mirroring `AGENT_API_KEY`'s role among the env keys.
- **Env-key fallback path**: when no header matches a DB token, `HasScope` falls back to whichever `*_API_KEY` Django setting the route declares (e.g. `ANALYSIS_API_KEY`, falling back further to `AGENT_API_KEY`). If that setting has a value, the raw header is compared with `secrets.compare_digest` (constant-time); if it's empty, the request is allowed through (see threat model item 1/4).
- **Storage**: `ApiToken.key_hash` is the only persisted form of a key — there is no plaintext column. `ApiToken.generate()` (`core/models.py`) mints a random token and returns the plaintext once, but nothing in the codebase calls it today; the only way tokens actually get created is [`seed_api_keys`](#issue--seed), which registers a hash for a value the operator already chose (see below) rather than generating a new secret.
- **Session path (spec 036 FR-2 / BL-20260503-13)**: with no `X-API-Key` header, `ApiKeyAuthentication` delegates to DRF's `SessionAuthentication`, so an authenticated Django session is a credential in its own right and satisfies `HasScope` on every gated router. CSRF is enforced by DRF on unsafe methods exactly as it is for the admin. A session is *additive*: with no session cookie the class behaves identically to spec 011, so key-only and anonymous callers are unaffected. `core.ApiToken` also gained a nullable `user` FK — a key bound to an owner authenticates *as* that user, which is what makes per-user quotas and ownership checks work for programmatic clients. The account routes themselves live at `/api/auth/{csrf,login,logout,me}` ([core/urls_auth.py](../backend/law_ai/core/urls_auth.py)) and are `AllowAny`, because they are what establishes identity. JWT/OAuth stays deferred (spec 036 RQ-1): the only client is first-party and same-origin, so a cookie beats a bearer token in browser storage.
- **Frontend**: no key reaches the browser (BL-20260430-07). `frontend/lib/api.ts::apiFetch` calls the same-origin proxy route `app/api/backend/[...path]/route.ts`, which forwards to `BACKEND_INTERNAL_URL` and attaches `X-API-Key` from a server-only `AGENT_API_KEY`. The agent-run WebSocket cannot be proxied by a route handler, so `app/api/ws-ticket/route.ts` mints a stream-scoped ticket that expires in 60s (`law_ai/core/ws_ticket.py` verifies it, and `AgentRunConsumer` still accepts a raw key or `X-API-Key` for non-browser clients). `NEXT_PUBLIC_AGENT_API_KEY` no longer exists.

## Scope matrix

`HasScope` (a DRF `BasePermission`) is parameterised per route by the `has_scope(scope, *fallback_envs)` factory in `law_ai.core.auth`, producing `RequireAgent` / `RequireAnalysis` / `RequireGraph` / `RequireLsat` — the module docstring notes these are "convenience factories matching the legacy `make_api_key_dep` helpers" (that older helper no longer exists; this is the current implementation). Scopes are bare strings (`ApiToken.SCOPE_*` in [core/models.py](../backend/law_ai/core/models.py)), not colon-suffixed.

| Route prefix         | Required scope | Per-route override env | Falls back to    | Notes |
|-----------------------|-----------------|--------------------------|-------------------|-------|
| `/api/agents/*`      | `agent`         | `AGENT_API_KEY`           | none              | Spec 008. Includes WS handshakes for `/ws/agents/{run_id}` and the ops dashboard channel `/ws/agents/ops`, authenticated separately (see below). |
| `/api/analysis`      | `analysis`       | `ANALYSIS_API_KEY`        | `AGENT_API_KEY`   | Spec 009. POST only; rate-limit candidate ([BL-20260503-12](../BACKLOG.md)). |
| `/api/graph/*`       | `graph`          | `GRAPH_API_KEY`           | `AGENT_API_KEY`   | Spec 009. Read-only neighborhood/path queries. |
| `/api/lsat/*`        | `lsat`           | `LSAT_API_KEY`            | `AGENT_API_KEY`   | Spec 009. Includes the tutor endpoint. Coaching tokens stream over the same Channels socket as analysis (`/ws/agents/{stream_id}`, authenticated by ticket), not over SSE — ADR 0001 and spec 011 chose WebSockets as the repo-wide push transport, so BL-20260503-03 shipped there rather than adding a second surface. |
| `/health`            | _(unauth)_       | —                         | —                 | Always public, no token required. |

An `agent`-scoped `ApiToken` (see [Authentication](#authentication)) satisfies every row above, same as `AGENT_API_KEY` does for the env-key fallback.

**WebSocket auth is separate and narrower.** `AgentRunConsumer` ([agentsapi/consumers.py](../backend/law_ai/agentsapi/consumers.py)) does not go through DRF at all: it reads `?api_key=` (or `?token=`) from the query string, or an `X-API-Key` handshake header for non-browser clients, and compares it against `AGENT_API_KEY` only — there is no `ApiToken`/DB lookup on the WS path, and per-router keys (`ANALYSIS_API_KEY`, etc.) don't apply to it. With `AGENT_API_KEY` unset the socket accepts any connection, matching the REST default-open posture.

## Share links (BL-20260429-26)

`GET /api/shared/<slug>` is the one deliberately unauthenticated route in the API. Its security rests on four properties, all in [analysis/urls_shared.py](../backend/law_ai/analysis/urls_shared.py) and [analysis/models.py](../backend/law_ai/analysis/models.py):

- **Only a signed-in user can mint one.** `POST /api/analysis/<id>/share` refuses anonymous and key-only callers, and refuses a run owned by someone else unless the caller is staff. So every public link has an accountable author.
- **A minted slug is 32 random bytes** (`secrets.token_urlsafe(32)`, ~256 bits), which puts enumeration out of reach. An owner may pick a readable slug instead — it is validated against `^[a-z0-9][a-z0-9_-]{2,63}$`, so a chosen slug can never smuggle a path segment, but a *guessable* slug is the owner's explicit choice.
- **Revocation is immediate and permanent.** `DELETE /api/analysis/<id>/share/<slug>` stamps `revoked_at`; the row is never deleted, so the slug stays taken and a dead link cannot be revived under a new owner. Archiving the run, or clearing its `shareable` flag, kills every link to it.
- **Every refusal is the same 404.** Revoked, archived, unshareable and never-minted are indistinguishable to a caller, so probing the endpoint learns nothing.

Deployments handling matters under a confidentiality obligation set `ANALYSIS_SHAREABLE_DEFAULT=false`: newly persisted runs are then marked unshareable and minting is refused for all of them (spec 036 NFR-PRIV-1). The shared payload always carries the not-legal-advice disclaimer, because a reader arriving from a link has none of the Studio's context.

## Token lifecycle

### Issue / seed

There is no "mint a brand-new token" command today. The operator picks the plaintext value (e.g. `openssl rand -hex 32`) and sets it as the relevant env var; `seed_api_keys` then registers a hashed `ApiToken` row so the DB-token auth path recognizes it too. The command takes **no flags** — it unconditionally reads all four settings and seeds whichever are non-empty:

```bash
# 1. Set your own random values, e.g. in .env or a secrets manager:
#    AGENT_API_KEY=<random>  ANALYSIS_API_KEY=<random>  GRAPH_API_KEY=<random>  LSAT_API_KEY=<random>
# (any of ANALYSIS/GRAPH/LSAT left unset falls back to AGENT_API_KEY at request time.)

# 2. Register ApiToken rows for whatever is set:
docker compose run --rm backend python manage.py seed_api_keys
# seed_api_keys: created=2 already_present=0
```

It never prints a plaintext token — there's nothing to print, since the operator supplied the plaintext in step 1. Internally it's `ApiToken.objects.get_or_create(key_hash=sha256(value), defaults={"scope": ..., "name": "env"})` per non-empty setting, so it's idempotent on the **hash**, not on any label: re-running with unchanged env values is a no-op, and changing an env value creates a *new* row rather than mutating the old one (the old row is left as-is, still valid, until explicitly revoked — see [Rotate](#rotate)).

### Rotate

There is no dedicated rotate command; rotation is "issue the new value, then revoke the old row":

1. Set a new value for the relevant `<ROUTER>_API_KEY` in the secrets manager / `.env`.
2. Re-run `seed_api_keys` — this seeds a new `ApiToken` row for the new hash. It does **not** touch the old row.
3. Roll the new value out to clients (env var update + `docker compose restart backend frontend`).
4. Revoke the old row (see below) — until you do, both the old and new values authenticate successfully.

### Revoke

No `revoke_api_key` management command exists yet. Today, revoke a DB token via the Django admin (`/admin/core/apitoken/`, set `Revoked at`) or the shell:

```python
from django.utils import timezone
from law_ai.core.models import ApiToken

ApiToken.objects.filter(key_hash=ApiToken.hash_key("<old-plaintext-key>")).update(
    revoked_at=timezone.now()
)
```

`ApiKeyAuthentication.authenticate` filters on `revoked_at__isnull=True`, so a revoked row is immediately rejected on the DB-token path.

**Sharp edge**: revoking the DB row alone does **not** fully lock the key out. When `ApiKeyAuthentication` can't find a matching, non-revoked `ApiToken`, `request.auth` stays `None`, and `HasScope` then falls through to the env-key comparison (`secrets.compare_digest` against the live `*_API_KEY` setting). If that setting still holds the old value, the old key keeps working through the fallback path even after its `ApiToken` row is revoked. Full revocation of a compromised key requires **also** rotating the underlying `*_API_KEY` env value and restarting the backend — not just flipping `revoked_at`.

## Rate limiting (BL-20260811-06, BL-20260503-12)

LLM-invoking endpoints (`/api/analysis`, the LSAT tutor and its siblings) carry `ScopedActorRateThrottle` ([core/throttling.py](../backend/law_ai/core/throttling.py)) on the `llm` scope. It buckets on the narrowest principal it can prove:

1. a provisioned `ApiToken` → its `key_hash` (`throttle_llm_key:<sha256>`);
2. a signed-in Django user → their pk (`throttle_llm_user:<pk>`);
3. neither → the client IP (`throttle_llm_ip:<addr>`), as before.

Two consequences worth stating plainly. First, DRF's stock `ScopedRateThrottle` reads `request.user.pk` once `is_authenticated` is true — and `_AnonymousActor` had no `pk`, so a request carrying a provisioned key raised `AttributeError` on every throttled view. No test sent a key at a throttled route, so it sat latent; the new class (and a `pk` on the actor) closes it. Second, per-IP buckets under-serve everyone behind a shared proxy, which is why an identified caller also gets the more generous `llm_keyed` rate (`LLM_KEYED_THROTTLE_RATE`, default 60/min) instead of the anonymous `LLM_THROTTLE_RATE` (20/min). A single `ApiToken` may override both through its `rate_limit` column (a DRF rate string such as `"200/min"`).

`django-ratelimit` was deliberately not added: DRF's throttle already owns the cache and the 429, and the only thing missing was the cache key.

## Stored settings (BL-20260830-07)

`/api/settings/values` persists the setting rows the shell used to keep only in `localStorage` ([core/urls_settings.py](../backend/law_ai/core/urls_settings.py)). The precedence engine stays in TypeScript (`frontend/lib/scope/resolver.ts`) — the backend decides only which rows exist and who may write them, which makes the authorisation surface small and explicit:

- **Read** returns the caller's scope chain and nothing else: `instance:local` for everyone, plus `user:<pk>` for a signed-in caller. Another user's rows are never in the response.
- **Write** to `user:<pk>` is allowed only when that pk is the caller's — this is the item's IDOR surface, and it is checked on every `PUT` and `DELETE`. The `user:me` alias exists so a client never has to send a pk it might get wrong.
- **Write** to `instance:local` is staff-only: an instance default (especially a `locked` one) overrides every user.
- **Anonymous** callers read instance rows and can write nothing, so the shell's localStorage-only behaviour without accounts is unchanged.
- Values are capped at 4KB and must be JSON-serialisable; every write and delete is provenance-logged as `setting_value.updated` / `setting_value.deleted` with the actor.

## Matters, export and account deletion (BL-20260817-01)

Matters hold client facts, so `/api/matters/*` accepts **only a signed-in session or a user-bound `ApiToken`** — a scope key never reaches them — and every lookup filters by `owner=request.user`. A slug that belongs to someone else answers 404, identical to one that never existed, so the URL cannot be used to test whether a matter exists. Matters are never resolvable by a public share slug; that surface exists for analyses only.

`GET /api/matters/<slug>/export` and `GET /api/account/export` are the portability half: one JSON bundle carrying the matter, its artifacts (with their provenance `trace_id`s), authorities, tasks and a merged timeline, logged as `matter.exported`.

`POST /api/account/delete` is the other half, and it deliberately does **not** call `user.delete()`. That would cascade away rows constitution §4 makes permanent, and the `PROTECT` FK on matter ownership blocks it halfway through anyway. Instead [`core/accounts/deletion.py`](../backend/law_ai/core/accounts/deletion.py) separates the two kinds of data an account holds: personal data (LSAT attempt history, the caller's `user:<pk>` setting rows) is deleted outright, while records of what happened (audit events, HITL decisions, quarantine reviews, analyses) are kept and de-identified — the auth row survives with a scrubbed username, no usable password and `is_active=False`, so every FK stays valid and no history is rewritten. Matters are archived and reassigned to a `deleted-user` tombstone, API tokens are revoked, share links are killed, and the whole thing is one `account.deleted` provenance event. The endpoint requires the caller to retype their username, and it is session-only: a leaked API key must never be able to end an account.

## Auditability

`AuditEvent` ([backend/law_ai/audit/models.py](../backend/law_ai/audit/models.py)) has five columns: `kind`, `timestamp`, `trace_id`, `agent_version`, `payload` (JSONField holding the full event). There is no `key_hash`, `route`, `method`, `status_code`, or `actor_label` column.

`ProvenanceMiddleware` calls `ProvenanceLogger.log_request` on every HTTP request/response, writing a `kind="http_request"` row whose `payload` is `{timestamp, request_id, method, path, client_ip, status_code, user_agent, type}`. **This does not capture which token (if any) authenticated the request** — there is currently no field on the HTTP audit row that ties it back to a `key_hash` or `ApiToken`, so tracing "who made this request" from the audit log alone isn't possible today; you'd need to correlate `client_ip`/`timestamp` against access logs out of band.

Operators can browse recent activity via the Django admin (`/admin/audit/auditevent/`) or query directly — `path`, `method`, and `status_code` are nested inside `payload` (JSONB), not top-level columns:

```sql
SELECT payload->>'path' AS path, count(*), max(timestamp) AS last_seen
FROM audit_auditevent
WHERE kind = 'http_request' AND timestamp > now() - interval '7 days'
GROUP BY payload->>'path'
ORDER BY last_seen DESC;
```

## LLM provider credentials

Runtime model calls route through the ordered chain in `LLM_PROVIDER_CHAIN` (default `claude_code,anthropic_api,xai,ollama`), implemented in `law_ai.core.llm`. The two Claude tiers share one transport, `law_ai.core.claude_code`, with two independent credentials:

- **`CLAUDE_CODE_OAUTH_TOKEN`** — a Claude subscription token minted with `claude setup-token`, sent as `Authorization: Bearer <token>` plus the `anthropic-beta: oauth-2025-04-20` header. Tried first.
- **`ANTHROPIC_API_KEY`** — a standard Anthropic API key, sent as `x-api-key`. Tried second, when the OAuth tier is unset or fails.

Both are read once per call via `settings_proxy` (`django-environ` → `settings/base.py`), never persisted to a database row, and never written to the audit log or application logs — the `llm_call` provenance event records the provider name, model, and latency, not the credential. If neither Claude credential is usable, the chain falls through to the xAI tier (below) and then to local Ollama (`OLLAMA_BASE_URL`), which sends no data off the machine.

### The xAI tier (draft review)

Tier 3 (`xai`) is Grok over a **subscription OAuth token**, not an API key: `make xai-login` runs a device-code grant against `https://auth.x.ai` reusing the public Grok-CLI desktop client id and stores the result at `XAI_CREDENTIALS_PATH` (default `.xai/credentials.json`, gitignored) — the one runtime credential in this list that lands on disk rather than staying in the environment. Treat that file as a secret: it holds a refresh token that mints access tokens for the whole subscription, not just this app. `XAI_ACCESS_TOKEN` / `XAI_REFRESH_TOKEN` can supply it from the environment instead. The tier is inert until that login runs, so a deployment that never authorises it never sends anything to xAI.

Data handling on this path is **not yet accepted** (`BL-20260904-03`). What xAI publishes for its developer API says calls are *"stored on our servers (encrypted at rest) for 30 days for auditing purposes"* and that *"xAI never trains on your API inputs or outputs without your explicit permission"* ([docs.x.ai — FAQ · API Security](https://docs.x.ai/developers/faq/security), read 2026-09-05, no effective date on the page). What is unresolved is whether those developer-API commitments govern a call authorised by a *consumer subscription* token, because `https://x.ai/legal/terms-of-service` and `https://x.ai/legal/privacy-policy` return HTTP 403 to automated fetches and were not read. There is no DPA for this path and no account-level Zero Data Retention setting available to it. The full write-up and the options are in [ADR 0007](adr/0007-xai-runtime-provider.md#terms-of-service-and-data-retention-review); until an owner records a decision there, treat the xAI tier as a third-party egress path with unreviewed terms.

**Confidentiality-bound data**: per [docs/constitution.md](constitution.md) §1, any matter under an obligation forbidding third-party processing **must** pin `LLM_PROVIDER_CHAIN=ollama` — this disables both Claude tiers *and* the xAI tier outright rather than relying on them simply being unconfigured. The default chain now has two third-party vendors in front of the local tier, so the pin is the only configuration that keeps prompt text on the host. The LegalBench eval harness stays pinned to Ollama unconditionally so benchmark numbers stay comparable regardless of what an individual deployment's chain is set to.

## Hardening checklist (production)

- [ ] `ENVIRONMENT=production` set; `DJANGO_SETTINGS_MODULE=law_ai.settings.prod`.
- [ ] `AGENT_API_KEY` (and any per-router keys) set via secrets manager, not committed `.env` — **required**, not optional: see threat model item 1.
- [ ] `python manage.py seed_api_keys` run once at boot so the DB-token path recognizes the configured keys.
- [ ] HTTPS terminator in front of daphne (Caddy / Traefik / nginx).
- [ ] Per-token rate limiting enabled ([BL-20260503-12](../BACKLOG.md) — pending).
- [ ] Phoenix collector reachable at `PHOENIX_COLLECTOR_ENDPOINT` for trace audit.
- [ ] `LLM_PROVIDER_CHAIN` reviewed: pin to `ollama` for confidentiality-bound deployments, otherwise confirm `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY` are set via secrets manager if Claude tiers should be reachable.
- [ ] xAI tier decided: either leave it unauthorised (`make xai-login` never run — the tier stays inert), or read [ADR 0007's terms review](adr/0007-xai-runtime-provider.md#terms-of-service-and-data-retention-review) and record the acceptance before any client material can reach it; `XAI_CREDENTIALS_PATH` protected like a secret if it is authorised.
- [ ] `python manage.py check --deploy` exits 0.

## Related docs

- [docs/constitution.md](constitution.md) §1 (LLM provider chain), §4 (provenance/audit), §8 (security baselines).
- [docs/architecture.md](architecture.md) — auth layer in the API row of the Component Responsibility table.
- [specs/008-agent-api-auth/](../specs/008-agent-api-auth/) and [specs/009-extend-api-auth/](../specs/009-extend-api-auth/).
