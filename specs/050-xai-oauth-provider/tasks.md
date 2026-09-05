# Tasks: xAI Grok OAuth provider tier

- **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## Tasks

- [x] **T-001** — `core/xai_oauth.py`: constants (auth base, client id, scope, device/authorize/token URLs, loopback host:port), PKCE S256 helpers, `CredentialStore` with atomic `0600` write + env seeding. (**FR-3**, **FR-4**, **NFR-SEC-1**)
- [x] **T-002** — Device-code grant: `request_device_code()` + `poll_device_token()` with `authorization_pending` / `slow_down` / `access_denied` / `expired_token` handling, injectable `sleep`/`now`, deadline from `expires_in`. (**FR-2**, **AC-2**)
- [x] **T-003** — Loopback PKCE grant: authorize-URL builder with `state`/`nonce`/`plan=generic`, a one-shot `http.server` on `127.0.0.1:56121/callback`, state verification, code exchange. (**FR-3**)
- [x] **T-004** — Refresh: `refresh_tokens()` + `access_token()` with 120s skew, unsigned JWT `exp` decode, and cross-process single-flight under `fcntl.flock`. (**FR-5**, **FR-6**, **AC-3**)
- [x] **T-005** — `core/xai.py`: `generate()` against `/v1/chat/completions` with `response_format.json_schema` mapping, temperature pass-through, 429/5xx backoff honouring `retry-after`, and one 401→refresh→retry. Plus `probe()`. (**FR-7**, **FR-8**, **AC-4**, **NFR-COMPAT-1**)
- [x] **T-006** — `XaiProvider` in `core/llm/providers.py`, registered as `xai` in `PROVIDER_REGISTRY` with `configured()` / `unconfigured_reason()` / `model_for()` / `agenerate()` / `probe()`. (**FR-1**, **FR-10**, **NFR-AUDIT-1**)
- [x] **T-007** — Settings + `.env.example`: `XAI_*` block, default `LLM_PROVIDER_CHAIN=claude_code,anthropic_api,xai,ollama`; `settings/test.py` blanks credentials and points the store at a non-existent path; `.gitignore` the credentials file. (**FR-1**, **FR-11**, **NFR-PRIV-1**, **AC-5**)
- [x] **T-008** — `xai_login` (device-code default, `--loopback`, `--status`) and `validate_xai` management commands + `make xai-login` / `make validate-xai`. (**FR-9**)
- [x] **T-009** — Tests under `backend/tests/core/`: polling branches, credential store round-trip + rotation, 401 retry, chain skip when unconfigured, and a guard that the test settings leave the tier unreachable. (**AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**)
- [x] **T-011** — `XaiExecutor` for the LSAT content factory, routed through the chain pinned to `xai`, registered as `--executor xai`; tests in `backend/tests/lsat/test_factory_executors.py`. (**FR-12**)
- [x] **T-010** — Docs: flip ADR 0007 status to accepted/implemented, drop the "authorised, not yet implemented" language from constitution §1, refresh the chain listings in `AGENTS.md`, `CLAUDE.md`, `AO-SDLC_Outline_Guide.md` §4.1, `README.md`, `PRD.md`. (**FR-1**)

## Follow-ups Discovered

- **BL-20260904-04** — *test-gap, high* — The cross-process refresh lock is only proven in-process: `test_second_refresh_reuses_the_first_result` exercises the freshness shortcut, not two OS processes contending on `fcntl.flock`. A real daphne/Celery race replaying a rotated refresh token would still slip through.
- **BL-20260904-05** — *tech-debt, med* — `XAI_MODEL` defaults to `grok-4.6` with no discovery: an operator on a subscription that does not expose that id gets a 404 per request until they set the var. Probe `/v1/models` in `validate_xai` and name the reachable ids.
- **BL-20260904-06** — *test-gap, med* — Nothing asserts the loopback PKCE path end-to-end; `_serve_one_callback` and the state-mismatch rejection are untested because they need a real socket. Only the authorize-URL builder is covered.
- **BL-20260904-07** — *doc-gap, low* — `docs/claude-code-dev-llm.md` is now a misnomer: it documents the whole chain including a non-Claude tier. Rename to `docs/llm-provider-chain.md` and fix the inbound links.
- **BL-20260904-08** — *feature, low* — The xAI tier has no streaming path, same gap as the Claude tiers (`BL-20260811-20`). The WebSocket consumer still cannot stream from any hosted provider.
- **BL-20260905-01** — *tech-debt, med* — Live-measured xAI latency is 5-10x the Claude tiers (IRAC 56-103s), which forced `XAI_REQUEST_TIMEOUT_S=240`. Fine for a fallback, slow for interactive paths; evaluate a faster Grok model or ship streaming.
- **BL-20260905-02** — *test-gap, med* — `core.llm.__init__` re-exported every provider constant except `XAI`/`XaiProvider`; no test asserts the package surface matches `PROVIDER_REGISTRY`.

Mirrored into [BACKLOG.md](../../BACKLOG.md). Live end-to-end verification against a real SuperGrok subscription ran 2026-09-05; two defects it caught (the 60s timeout and the read-timeout retry) are fixed in this spec.
