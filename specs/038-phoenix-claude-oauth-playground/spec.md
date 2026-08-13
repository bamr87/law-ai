# Spec: Phoenix Playground on the Claude OAuth Tier

- **ID**: 038-phoenix-claude-oauth-playground
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: observability — let the Phoenix surface (specs 010/036) exercise the product's tier-1 Claude credential
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — no new vendor (§1: the credential is the already-sanctioned Claude OAuth tier; Phoenix is already self-hosted), no new Python dependency, the secret stays in `.env` and never enters the Phoenix container/UI/DB. One deliberate exception is recorded: playground calls do not pass through `law_ai.core.llm` and are therefore not provenance-audited — tracked as BL-20260811-33 rather than silently ignored.

## 1. Problem & Motivation

Spec 036 mirrored every prompt into Phoenix's prompt store, but the Phoenix **playground** cannot run them: it can only authenticate to Anthropic with a plain API key sent as `x-api-key`, while the product's tier-1 credential (`LLM_PROVIDER_CHAIN` head) is a Claude subscription OAuth token that the API only accepts as `Authorization: Bearer` **plus** the `anthropic-beta: oauth-2025-04-20` header (`law_ai/core/claude_code.py` — "sending the wrong pair is a 401"). There is no supported way to hand Phoenix an OAuth token: its Anthropic provider reads `ANTHROPIC_API_KEY` only.

The user's ask — "configure Arize to use the Claude OAuth key" — therefore needs a bridge, not a config value.

## 2. Goals

- G1: The Phoenix playground authenticates to Anthropic with the same Claude OAuth token the runtime chain uses, with **zero per-user UI configuration**.
- G2: The token never leaves `.env` — not into the Phoenix container's env, UI, browser storage, or database.
- G3: Streaming (SSE) and rate-limit backoff semantics survive the bridge.

## 3. Non-Goals

- NG1: Provenance/audit events for playground LLM calls (recorded as BL-20260811-33; playground traffic is observable via `docker compose logs claude-oauth-proxy`).
- NG2: Tier-2 (`ANTHROPIC_API_KEY`) fallback inside the proxy when the OAuth token is absent (BL-20260811-34).
- NG3: Changing anything about the product runtime chain — `law_ai.core.llm` is untouched.
- NG4: Exposing the proxy outside the compose network.

## 4. User Stories

- As a prompt engineer, I want to open a spec-036-synced prompt in the Phoenix playground and run it against Claude, so that prompt iteration happens where the traces and versions already live.
- As an operator, I want the OAuth secret confined to `.env` and one internal sidecar, so that adding playground capability does not widen the credential's blast radius.

## 5. Functional Requirements

- **FR-1**: A sidecar ASGI service (`backend/scripts/claude_oauth_proxy.py`, compose service `claude-oauth-proxy`) accepts Anthropic-API-shaped HTTP requests, strips any caller credentials (`x-api-key`, `authorization`), and forwards them upstream with `Authorization: Bearer $CLAUDE_CODE_OAUTH_TOKEN` + merged `anthropic-beta` header (OAuth flag first, caller flags preserved).
- **FR-2**: The proxy streams upstream responses back unmodified (status, body, SSE chunks) and relays only safe headers (`content-type`, `cache-control`, `request-id`, `retry-after`).
- **FR-3**: The `phoenix` compose service routes its Anthropic traffic to the proxy via `ANTHROPIC_BASE_URL=http://claude-oauth-proxy:8080` with a placeholder `ANTHROPIC_API_KEY`, so the stock playground UI works with no per-model `baseUrl` fiddling (Phoenix 12.9.0's Anthropic client honors the SDK-level base-URL env var — verified live).
- **FR-4**: The proxy is internal-only (`expose`, no host `ports`), health-checked at `/health`, and degrades loudly: 503 with an actionable message on every API route when `CLAUDE_CODE_OAUTH_TOKEN` is unset, 502 when upstream is unreachable.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: The token is read only from the proxy's own env (`.env` via `env_file`); it is never logged, never relayed in responses, and does not appear in the Phoenix container's environment.
- **NFR-SEC-2**: No new Python dependency — `httpx` + `daphne` (both existing backend deps) serve the proxy.
- **NFR-TEST-1**: The full request/response path is unit-tested via `httpx.ASGITransport` with a respx-mocked upstream — no live Anthropic traffic in the suite.

## 7. Data Model Impact

None. No schema changes anywhere; the proxy is stateless.

## 8. API Surface

No new Django routes. New internal-only service surface: `claude-oauth-proxy:8080` inside the compose network — `GET /health`, plus transparent passthrough of `POST /v1/messages` (and any other Anthropic path Phoenix calls).

## 9. Agent / Crew Impact

None. No agent or runtime code path changes; the proxy is reachable only from the compose network and nothing in `law_ai` calls it.

## 10. Acceptance Criteria

- **AC-1**: A Phoenix playground `chatCompletion` against provider `ANTHROPIC` (no explicit `baseUrl`) produces a request that traverses the proxy and is **authenticated** by the real Anthropic API — verified live: proxy logs show `POST /v1/messages` forwarded, and the API answered with org-attributed responses (a `rate_limit_error` carrying a `request_id`, which an invalid credential could never produce — bad auth returns 401 `authentication_error`).
- **AC-2**: Unit tests prove the header contract: placeholder `x-api-key` stripped, `Bearer` + `oauth-2025-04-20` injected, caller beta flags merged after the OAuth flag, `retry-after` relayed, SSE bodies byte-identical.
- **AC-3**: With `CLAUDE_CODE_OAUTH_TOKEN` unset, `/health` and API routes return 503 with an actionable message (fresh clones boot; the healthcheck surfaces the gap).
- **AC-4**: The compose stack starts with `phoenix` depending on the proxy, and the proxy publishes no host port.

## 11. LegalBench Impact

None — the eval harness remains pinned to Ollama and no runtime path changed.
