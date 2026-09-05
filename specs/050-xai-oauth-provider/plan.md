# Plan: xAI Grok OAuth provider tier

- **Spec**: [spec.md](spec.md)
- **Status**: shipped

## Architecture

Two new modules, mirroring the split the Claude tiers already use (`core/claude_code.py` transport + `core/llm/providers.py` adapter). Nothing else moves.

```
core/xai_oauth.py   credential lifecycle only — no chat calls
                    ├── device-code grant  (RFC 8628)     ← headless / Docker
                    ├── loopback PKCE grant (S256)        ← host with a browser
                    ├── CredentialStore: atomic 0600 JSON + flock
                    └── access_token(): refresh-if-expiring, single-flight

core/xai.py         chat transport — OpenAI-compatible /v1/chat/completions
                    ├── generate()  ← retries, 401→refresh→retry once
                    └── probe()     ← near-free reachability for the dashboard

core/llm/providers.py
                    └── XaiProvider  → registered as "xai" in PROVIDER_REGISTRY

core/management/commands/xai_login.py     device-code by default, --loopback opt
core/management/commands/validate_xai.py  probe + one real round trip
```

The router, provenance, health endpoint and dashboard need **no changes** — they iterate `PROVIDER_REGISTRY` and the chain string, so a registered provider appears everywhere automatically. That is the whole reason spec 034 built a registry.

## Key decisions

**Device-code is the primary path, not the fallback.** Kilo defaults to the loopback flow because it runs on the user's desktop. We are Docker-first: `127.0.0.1:56121` inside the backend container is not the browser's loopback, and the redirect URI is fixed by the client registration so it cannot be re-pointed at the host. Device-code needs no inbound path at all, so `make xai-login` uses it and `--loopback` is the opt-in for host-side login.

**One credentials file, locked.** xAI rotates the refresh token on every use: two processes refreshing concurrently means one of them replays a consumed token and dies. Kilo solves this in-process (`refreshPromise`) and documents the cross-process case as a known limitation. We have daphne *and* Celery workers against one mounted file, so in-process single-flight is not enough — `CredentialStore.refresh()` takes an exclusive `fcntl.flock` on the credentials file, re-reads under the lock, and returns the other process's fresh token if one landed while we waited.

**Unsigned JWT decode, scheduling only.** The access token is a JWT; reading `exp` without verifying the signature tells us when to refresh. It never gates trust — an attacker who could forge that claim gains only an early refresh. Opaque (non-JWT) tokens fall back to the stored `expires` and, ultimately, to the reactive 401 path.

**Reuse the public Grok-CLI client id.** xAI rejects loopback OAuth from non-allowlisted clients, so every open implementation of this flow uses the desktop client id xAI ships, with `plan=generic` on the consent screen. We follow suit and set `referrer=law-ai` for best-effort attribution in xAI's logs. NG4 records that we are not registering our own client.

**Temperature is forwarded here.** The Claude transport deliberately drops sampling params (removed on current Claude models, 400 if sent). xAI is OpenAI-compatible and accepts `temperature`, so `LLMRequest.temperature` is passed through rather than silently ignored.

**A long timeout, and no retry on a read timeout.** *(Both corrected after live verification on 2026-09-05 — the first draft copied the Claude tiers' 60s and retried every transport error.)* Grok is a reasoning model and is far slower than Claude on this product's work: a full IRAC analysis measured **56–103s** live, and item authoring 68s. At 60s every attempt read-timed-out, and retrying replayed the same slow work — one analysis cost ~183s before the chain gave up and `LegalAnalyst` degraded to its offline fallback, i.e. the tier looked broken while actually working. `XAI_REQUEST_TIMEOUT_S` therefore defaults to 240s, and `httpx.ReadTimeout`/`PoolTimeout` are **not** retried: a read timeout means xAI accepted the request and is still thinking, so the useful move is to fall through to the next tier once rather than three times. Genuine transient faults (`ConnectError`) keep their retries.

## Failure model

| Condition | Behaviour |
| --- | --- |
| No credentials file, no env seed | `configured()` false → router skips the tier with a reason (AC-1) |
| Refresh token rejected (rotated away / revoked) | tier raises `LLMUnavailableError`; router records and falls through to Ollama |
| 403 from xAI's OAuth allowlist | same — a recorded tier failure, never a 500 (NFR-COMPAT-1) |
| 401 mid-call | one refresh + one retry, then fall through (FR-8) |
| 429 / 5xx | exponential backoff honouring `retry-after`, then fall through |
| Device authorization denied / expired | `xai_login` exits non-zero with the RFC 8628 reason; nothing is written |

## Test strategy

Unit only — no live xAI in CI, and `settings/test.py` makes that structural (FR-11). `httpx.MockTransport` drives the token endpoint so the polling branches (`authorization_pending`, `slow_down`, `access_denied`, `expired_token`, deadline) are exercised without real waits by injecting `sleep` and `now`, exactly as Kilo's own tests do. Credential-store tests use `tmp_path`; the lock path is exercised by refreshing twice and asserting one HTTP call.

## Rollout

The default chain flip (`BL-20260904-02`) lands in this spec, so a deployment that has not pinned `LLM_PROVIDER_CHAIN` gains the tier on upgrade. It is inert without credentials — an unconfigured tier is skipped — so the flip cannot change behaviour for anyone who has not run `xai-login`.
