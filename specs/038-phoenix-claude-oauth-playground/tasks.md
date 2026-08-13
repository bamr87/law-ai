# Tasks: Phoenix Playground on the Claude OAuth Tier

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.

---

## T-001 — Sidecar proxy: OAuth header translation + streaming relay

- **Refs**: FR-1, FR-2, FR-4, NFR-SEC-1, NFR-SEC-2, AC-2, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/scripts/claude_oauth_proxy.py` (new)
- **Steps**:
  1. Pure-ASGI app: `/health`, credential swap (`x-api-key`/`authorization` stripped; `Bearer` + merged `anthropic-beta` injected), streaming body relay, safe-header allowlist incl. `retry-after`.
  2. 503 with actionable message when `CLAUDE_CODE_OAUTH_TOKEN` unset; 502 on upstream connect failure. Token never logged.
- **Verify**: `docker compose run --rm backend pytest tests/scripts -q --no-cov` green.

## T-002 — Compose wiring: internal-only service + Phoenix routing

- **Refs**: FR-3, FR-4, AC-1, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `docker-compose.yml` (edit — `claude-oauth-proxy` service; `phoenix` env + `depends_on`)
- **Steps**:
  1. Proxy service reuses the backend image, mounts `.env` via `env_file`, runs `python -m daphne … scripts.claude_oauth_proxy:application`, `expose: 8080` only, exec-form healthcheck.
  2. Phoenix gets `ANTHROPIC_BASE_URL=http://claude-oauth-proxy:8080` + placeholder `ANTHROPIC_API_KEY`.
- **Verify**: `docker compose up -d claude-oauth-proxy phoenix` → both `(healthy)`; `docker compose ps` shows no host port on the proxy.

## T-003 — Unit tests over the full ASGI path

- **Refs**: NFR-TEST-1, AC-2, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/tests/scripts/__init__.py` (new)
  - `backend/tests/scripts/test_claude_oauth_proxy.py` (new — 8 tests)
- **Verify**: `docker compose run --rm backend pytest tests/scripts -q --no-cov` → 8 passed; `ruff`/`black` clean on the new files.

## T-004 — Live verification through Phoenix

- **Refs**: FR-3, AC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Steps**:
  1. `manage.py validate_claude_code` → OAuth tier reachable end-to-end (baseline).
  2. Phoenix GraphQL `chatCompletion` (provider `ANTHROPIC`, no `baseUrl`) → proxy logs `POST /v1/messages` → API responds org-authenticated. Repeated with explicit `baseUrl`; both routes traverse the proxy.
  3. Rate-limit caveat: the subscription window was exhausted at verification time (429 + `request_id` — authenticated), so the content 200 is pinned by unit tests instead; re-run any playground prompt after the window resets for a visible completion.
- **Verify**: `docker compose logs claude-oauth-proxy` shows the forwarded calls and upstream statuses.

## T-005 — Docs

- **Refs**: FR-3, NFR-SEC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `docs/architecture.md` (edit — playground credential path row)
  - `.env.example` (edit — note that the playground reuses `CLAUDE_CODE_OAUTH_TOKEN` via the proxy)
- **Verify**: `make lint-specs` green; docs mention the sidecar by name.

---

## Done-When (Definition of Done)

- All tasks `[x]`; `make lint` + targeted tests green; `make lint-specs` green.
- No LegalBench delta (harness untouched).
- The §11 loop below is populated and mirrored into BACKLOG.md.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260811-33 — feature, med — playground LLM calls bypass the provenance audit layer; emit `llm_call`-equivalent events from the proxy or record a constitutional exemption for observability tooling.
- BL-20260811-34 — feature, low — proxy speaks only the OAuth tier; mirror the runtime chain's tier order by falling back to `ANTHROPIC_API_KEY` passthrough when the token is absent.
- BL-20260811-35 — test-gap, low — lock in the compose wiring contract (phoenix `ANTHROPIC_BASE_URL` → proxy DNS name → `expose`-only) with a structure test over `docker-compose.yml`.
