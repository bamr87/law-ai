---
name: run-law-ai
description: Build, run, drive, and test the Law AI app (Django/daphne API + agents). Use when asked to run law_ai / law-ai, start the backend or API, smoke-test the endpoints, drive an agent (LSAT tutor/author, LegalAnalyst), or check that the app boots.
---

Law AI is a Docker-first, multi-agent legal-intelligence platform: a Django 5 ASGI (daphne) **HTTP API** at `:8000` plus a Next.js frontend at `:3000`. The agent-driveable surface is the API. Drive it with the committed driver **`.claude/skills/run-law-ai/driver.sh`**, which launches daphne in a throwaway container (SQLite, no heavy deps) and curl-smokes the public endpoints. All paths below are relative to the repo root.

> Everything runs inside Docker via `docker compose` / `make` — never `pytest`,
> `pip`, `python manage.py`, etc. on the host (see [CLAUDE.md](../../../CLAUDE.md)).

## Prerequisites

On the host: `docker` + `docker compose` v2, plus `curl`, `python3`, and `make` (used by the driver and the agent demos). No host-level Python/Node setup — the backend image carries all app dependencies. The image auto-builds on the first `docker compose run` (a few minutes); to pre-build explicitly:

```bash
docker compose build backend
```

## Run (agent path) — the driver

```bash
bash .claude/skills/run-law-ai/driver.sh
```

Launches the API (daphne + SQLite + `--no-deps`, telemetry and the Claude Code provider forced off for determinism), waits for `/health`, then smoke-tests the public surface and tears down. Verified output:

```
[driver] API is up.
  PASS  GET   /health                            200
  PASS  GET   /api/lsat/sections                 200
  PASS  GET   /api/lsat/questions?limit=2        200
  PASS  GET   /api/agents                        200
  PASS  GET   /api/agents/health/local-ai        200
  PASS  GET   /api/analysis                      405
  PASS  POST  /api/analysis                      200
  PASS  POST  /api/lsat/grade                    200
  PASS  POST  /api/lsat/tutor                    200
  sections: ['LR', 'RC', 'LG']
  agents:   ['IngestionScout', 'LSATContentAuthor', 'LegalAnalyst', 'PrecedentHunter']
[driver] ✅ ALL CHECKS PASSED
```

**Keep it running to poke it yourself:**

```bash
KEEP=1 bash .claude/skills/run-law-ai/driver.sh   # leaves the API up at :8000
curl -s http://localhost:8000/api/lsat/sections | python3 -m json.tool
curl -s -X POST http://localhost:8000/api/analysis \
  -H 'Content-Type: application/json' \
  -d '{"text":"Is leaving a wet floor unmarked negligence?"}' | python3 -m json.tool
docker rm -f law-ai-driver-api                           # stop it
```

The API is **default-open** in dev (no `*_API_KEY` set), so curl needs no auth. `POST /api/analysis` runs the `LegalAnalyst` IRAC agent through the HTTP layer.

## Drive the agents with a real LLM (optional)

These `make` targets run agents through their full pipeline. They call the product `LLM_PROVIDER_CHAIN` unconditionally (Claude OAuth → `ANTHROPIC_API_KEY` → xAI Grok → Ollama, constitution §1) — set `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in `backend/.env` for a live Claude run, or run `make xai-login` for the Grok tier (see [docs/llm-provider-chain.md](../../../docs/llm-provider-chain.md)); with neither configured and no reachable Ollama they degrade to a deterministic offline draft, so they still run on a clean clone.

```bash
make legal-analyst-demo                      # LegalAnalyst → IRAC analysis
make lsat-author-demo                        # LSATContentAuthor → drafts an LSAT question
make validate-claude-code                    # validate the Claude Code OAuth connection
make lsat-author-demo ARGS='--section LG --passage-id lg-game-001'
```

Verified `make legal-analyst-demo` output (with a token present it runs live):

```
Running LegalAnalyst (IRAC)…
Result (via Claude Code):
  confidence : 0.82
  Issue       : Whether an arbitration clause … is enforceable …
```

## Run (human path) — full stack

```bash
make dev      # frontend :3000, API :8000 (Swagger at :8000/docs)
make down     # stop
```

`make dev` brings up the **entire** stack (postgres, neo4j, redis, ollama, phoenix, backend, frontend). Use it when you need the graph/ingestion features, which really do need Neo4j and Ollama. For a GUI check alone it is more machine than you need — see below.

## Run the GUI (headless) — `FRONTEND=1`

```bash
FRONTEND=1 bash .claude/skills/run-law-ai/driver.sh
```

The API-only driver never touched :3000, so a broken frontend passed silently. `FRONTEND=1` additionally starts the compose `frontend` service with `--no-deps`, points its server-side `BACKEND_INTERNAL_URL` at the driver's API container, and asserts on the rendered pages (BL-20260615-04). Verified output:

```
[driver] launching Next.js GUI (--no-deps) on :3000…
[driver] GUI is up.
[driver] GUI smoke (status + rendered marker):
  PASS  /                        200, matched Law AI
  PASS  /lsat                    200, matched LSAT
  PASS  /analysis                200, matched analysis
  PASS  /api/backend/…/sections  200 (Next → law-ai-driver-api)
```

The last line is the one that matters most: it exercises the browser → Next proxy → Django hop (`frontend/app/api/backend/[...path]/route.ts`), so a misrouted proxy shows up here rather than as a blank screen in a browser.

Ports are overridable — `PORT=8010 FPORT=3010 FRONTEND=1 …` — which is how you run this beside a live `make dev` stack that already owns 8000/3000.

**Looking at it in a browser.** There is no `chromium-cli` in this repo; the sanctioned agent browser is the **Playwright MCP plugin**. Run the driver with `KEEP=1 FRONTEND=1`, then drive the live page:

```
mcp__plugin_playwright_playwright__browser_navigate  → http://localhost:3000/lsat
mcp__plugin_playwright_playwright__browser_snapshot  → accessibility tree
mcp__plugin_playwright_playwright__browser_take_screenshot
```

Use the curl smoke as the mechanical gate and the browser only when you need to *see* something. For a real regression suite use `make test-e2e` (Playwright, see [docs/e2e-testing.md](../../../docs/e2e-testing.md)) — this driver is a boot check, not a test suite.

### Should the launch logic move into `scripts/`?

`BL-20260615-04` asked that to be considered "if the e2e suite wants to reuse it". It does not, and the answer is no. `make test-e2e` (Makefile) brings up its own stack with `docker compose --profile e2e up -d --wait frontend backend-e2e`, overriding `FRONTEND_BACKEND_URL` so the browser talks to the pinned-degraded `backend-e2e` sidecar. That is a different launch in every respect that matters:

| | `driver.sh` | `make test-e2e` |
|---|---|---|
| Containers | two throwaway `docker compose run` containers, `--no-deps` | the compose services themselves, `up -d --wait` |
| Databases | none — SQLite in the API container | real Postgres, Neo4j, Redis |
| Backend | this driver's own API container, offline deterministic LLM | the `backend-e2e` sidecar, pinned to an unreachable Ollama |
| Lifetime | torn down on exit unless `KEEP=1` | left up for `make test-e2e-down` |
| Purpose | does the app boot and serve | does the app behave |

Extracting a shared launcher would have to abstract over all five rows, and the only caller that would use the abstraction is the one it was extracted from. So the launch logic stays here, in the one script that needs it, and this paragraph is the record of the decision rather than a `scripts/` helper nobody imports. Revisit it if a second caller ever wants a throwaway no-deps stack — `tests/test_run_law_ai_driver.py` will hold the contract steady in the meantime.

## Test

The backend suite runs in a container. For an isolated run that doesn't need the compose Postgres, override `DATABASE_URL` to SQLite (verified form):

```bash
docker compose run --rm --no-deps \
  -e DATABASE_URL=sqlite:///./test.sqlite3 -e PHOENIX_COLLECTOR_ENDPOINT= \
  backend pytest tests/api/test_lsat.py --no-header --no-cov -p no:cacheprovider -q
```

`make test-backend` runs the full suite but assumes the stack's Postgres is up. Single test: append `tests/path::test_name`. Lint/type: `make lint` / `make typecheck`.

## Gotchas

- **`docker compose run` starts ALL deps unless you pass `--no-deps`.** Without
it, postgres/neo4j/redis/**ollama** all spin up (slow, and they linger after). The driver uses `--no-deps`; the API needs none of them for the endpoints above.
- **The compose `backend` service injects `DATABASE_URL=postgres://…@postgres`,**
which overrides the settings' SQLite test default (env wins over `.env`). A bare `docker compose run backend pytest …` then fails with *"failed to resolve host 'postgres'"*. Pass `-e DATABASE_URL=sqlite:///./x.sqlite3` for a Postgres-free run.
- **Don't use the Dockerfile `CMD` verbatim for a light run** — it runs
`ensure_checkpointer`, which needs Postgres. The driver runs only `migrate --noinput && daphne …`, which is fine on SQLite.
- **Phoenix/OpenTelemetry spams `Failed to resolve 'phoenix'`** when the stack
isn't up. Set `-e PHOENIX_COLLECTOR_ENDPOINT=` (the driver does) to silence it — it's noise, not an error.
- **`DJANGO_SETTINGS_MODULE` defaults to `law_ai.settings.dev`** (DEBUG=True) via
`manage.py`/`asgi.py`. Claude/Ollama credentials are read the same way in every environment except `test`, which hard-blanks them (`settings/test.py`).
- **macOS hosts have no `timeout`** — don't wrap commands in it; rely on the
  tool/shell timeout instead.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to resolve host 'postgres'` | Add `-e DATABASE_URL=sqlite:///./run.sqlite3` (no Postgres needed for the API/LSAT routes). |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | `docker rm -f law-ai-driver-api`, or run the driver with `PORT=8001`. |
| Driver hangs at "waiting for /health" | `docker logs law-ai-driver-api` — usually a missing `-e DATABASE_URL` override or a migrate error. |
| Endless `Failed to resolve 'phoenix'` lines | Set `-e PHOENIX_COLLECTOR_ENDPOINT=`. |
| Agent demo says `via mock / fallback` | Expected when every `LLM_PROVIDER_CHAIN` tier is unreachable. For a live run, set `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in `backend/.env`, or have Ollama running. |
