# Spec: xAI Grok OAuth provider tier

- **ID**: 050-xai-oauth-provider
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-04
- **Roadmap Epic**: runtime resilience — a hosted fallback between Anthropic and the local model
- **Constitution Compliance**: authorised by [docs/constitution.md](../../docs/constitution.md) §1 as amended 2026-09-04 and [ADR 0007](../../docs/adr/0007-xai-runtime-provider.md). This spec **implements** that amendment; it does not extend it.

## 1. Problem & Motivation

[ADR 0007](../../docs/adr/0007-xai-runtime-provider.md) sanctioned xAI as default tier 3 of `LLM_PROVIDER_CHAIN` but blocked implementation on one unknown: the amendment specifies subscription-OAuth auth, and xAI's *published* API documents only a bearer `XAI_API_KEY`. `BL-20260904-01` carried that block.

The block is now resolved. Kilo Code implements exactly this flow in the open, at `packages/opencode/src/plugin/xai.ts` in [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode): an OAuth 2.0 flow against `https://auth.x.ai` using the public Grok-CLI desktop client, exchanging a SuperGrok / X Premium+ subscription for a bearer access token accepted by `https://api.x.ai/v1`. Both an RFC 8628 device-code path and a loopback PKCE path are exposed. This spec ports that flow into `law_ai.core`.

Today an Anthropic outage or rate-limit drops the product from Claude straight to a 7B local model — the quality cliff ADR 0005 accepted and ADR 0007 exists to soften.

## 2. Goals

- G1: `xai` is a working tier of the provider chain, authenticated by a subscription OAuth token.
- G2: A token can be acquired from inside the Docker-first workflow, with no browser reachable from the container.
- G3: Rotating refresh tokens survive concurrent processes (daphne + Celery workers) without invalidating each other.
- G4: The tier fails the way every other tier fails — recorded, then fallen through — never crashing a request.

## 3. Non-Goals

- NG1: Adding a vendor beyond Anthropic / xAI / Ollama. Constitution §1 still rejects that without a further amendment.
- NG2: Routing LegalBench through the chain. It stays pinned to Ollama (§1 reproducibility, §6).
- NG3: Streaming through the chain — the tier is request/response only, matching the Claude tiers (`BL-20260811-20` stays open).
- NG4: Registering our own xAI OAuth client. We reuse the public Grok-CLI client id, as the other open implementations of this flow do.
- NG5: Making xAI the default tier 1. Claude remains the default runtime (ADR 0007).

## 4. User Stories

- As an operator, I want the product to stay on a frontier model when Anthropic is down, so that an outage does not silently halve answer quality.
- As an operator on a VPS or in Docker, I want to authorise xAI without a browser on the box, so that headless deployments are not second-class.
- As an auditor, I want `xai`-served answers labelled as such in provenance, so that I can tell which vendor produced a given legal analysis.
- As a developer, I want the suite to be structurally unable to reach xAI, so that `make test` never bills a subscription.

## 5. Functional Requirements

- **FR-1**: An `xai` provider registered in `PROVIDER_REGISTRY`, occupying default chain position 3 — after both Anthropic tiers, before `ollama`. The shipped default becomes `claude_code,anthropic_api,xai,ollama`.
- **FR-2**: Device-code acquisition (RFC 8628) against `https://auth.x.ai/oauth2/device/code`, polling `https://auth.x.ai/oauth2/token` with `grant_type=urn:ietf:params:oauth:grant-type:device_code`, honouring `authorization_pending`, `slow_down`, `access_denied` and `expired_token` per §3.5, bounded by the server's `expires_in`.
- **FR-3**: Loopback acquisition as the alternate path: PKCE S256 against `https://auth.x.ai/oauth2/authorize` with `redirect_uri=http://127.0.0.1:56121/callback`, `state` and `nonce` verified on callback. The port is fixed because it is part of the client's registration.
- **FR-4**: Credentials persist to a JSON file (`XAI_CREDENTIALS_PATH`), written atomically at mode `0600`. `XAI_ACCESS_TOKEN` / `XAI_REFRESH_TOKEN` seed the store from the environment when no file exists.
- **FR-5**: Refresh (`grant_type=refresh_token`) is single-flight **across processes**, guarded by an exclusive lock on the credentials file, because xAI rotates the refresh token on every use and a replayed token is dead.
- **FR-6**: Proactive refresh when the stored expiry, or the access token's own unverified JWT `exp` claim, is within a 120s skew. The unsigned decode is used only to schedule a refresh, never to make a trust decision.
- **FR-7**: Chat completion via `POST https://api.x.ai/v1/chat/completions` with `Authorization: Bearer <access>`; `response_schema` maps to `response_format.json_schema`, and `temperature` is forwarded (unlike the Claude tiers, xAI accepts it).
- **FR-8**: Transient failures (429, 5xx) retry with exponential backoff and honour `retry-after`; a 401 triggers one reactive refresh-and-retry before giving up.
- **FR-9**: `xai_login` and `validate_xai` management commands, plus `make xai-login` / `make validate-xai`, mirroring `validate_claude_code`.
- **FR-10**: The provider reports `configured()` / `unconfigured_reason()` and a near-free `probe()`, so the local-ai health endpoint and agent dashboard list the tier like every other.
- **FR-11**: `settings/test.py` blanks every xAI credential and points the credentials path at a non-existent file, so the suite cannot reach xAI even on a developer box that is logged in.
- **FR-12**: The LSAT content factory can generate on the tier (`lsat_factory run --executor xai`). Unlike `ClaudeCodeExecutor`, which calls its transport directly, the xAI executor routes through `law_ai.core.llm` with the chain pinned to `providers=("xai",)` — the same reproducible single-provider attribution, but inside the §4 choke point and therefore in the `llm_call` audit trail.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: Access and refresh tokens are never logged, never included in an exception message, and never written world-readable.
- **NFR-PRIV-1**: `LLM_PROVIDER_CHAIN=ollama` remains sufficient on its own to guarantee no prompt text leaves the host. The xAI tier must be unreachable when it is not named in the chain.
- **NFR-AUDIT-1**: Every routed xAI call writes an `llm_call` provenance event naming provider `xai` and the model that served it, through the existing router — the tier adds no new audit path.
- **NFR-COMPAT-1**: xAI enforces its own allowlist on the OAuth API surface and can return 403 to a paying subscriber. That must degrade to a recorded tier failure and fall through to Ollama, never a 500.

## 7. Data Model Impact

None. No graph nodes, no migrations. The only new persistent state is the credentials JSON file, which is operator-local and gitignored.

## 8. Acceptance Criteria

- **AC-1**: With no credentials, `xai` is skipped by the router with a recorded reason and the chain still answers from another tier.
- **AC-2**: Device-code polling keeps polling on `authorization_pending`, widens its interval on `slow_down`, and raises on `access_denied` / `expired_token` / deadline.
- **AC-3**: A rotated refresh token is persisted, and a concurrent refresh in another process does not replay the consumed one.
- **AC-4**: A 401 on a chat call triggers one refresh and one retry, then falls through.
- **AC-5**: `make test` issues zero requests to `auth.x.ai` or `api.x.ai`.

## 9. Risks

- The reused Grok-CLI `client_id` belongs to xAI, not to us; xAI can revoke it or allowlist it away at any time. Mitigation: the tier is a fallback and its failure is an ordinary fall-through (NFR-COMPAT-1).
- The flow is undocumented by xAI, so endpoint shapes can change without notice. Mitigation: every endpoint is pinned in one module with injectable overrides, and `validate_xai` gives a one-command diagnosis.
- Cross-process refresh rotation is genuinely hard; the file lock narrows but does not eliminate the race between separate hosts sharing one credentials file.
- **Latency, measured live 2026-09-05**: IRAC analysis 56–103s, LSAT item authoring 68s, tutor coaching 13s, probe ~2s. That is 5–10× the Claude tiers and is slow enough to be a UX problem on interactive paths — acceptable for a *fallback* tier, which is all this is, but `BL-20260905-01` tracks it. It also forced `XAI_REQUEST_TIMEOUT_S=240` and the no-retry-on-read-timeout rule (see plan.md).

## 10. Constitution Compliance Notes

§1 — implements the sanctioned tier at the sanctioned position; Ollama stays last and `LLM_PROVIDER_CHAIN=ollama` still guarantees zero egress. §4 — all calls route through `law_ai.core.llm`; no new transport bypass. §6 — LegalBench untouched. §8 — no secrets in the repo; credentials are file-based and gitignored.
