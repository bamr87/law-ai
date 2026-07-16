---
name: run-law-ai
description: Build, run, drive, and test the Law AI app (Django/daphne API + agents). Use when asked to run law_ai / law-ai, start the backend or API, smoke-test the endpoints, drive an agent (LSAT tutor/author, LegalAnalyst), or check that the app boots.
---

Law AI is a Docker-first, multi-agent legal-intelligence platform: a Django 5
ASGI (daphne) **HTTP API** at `:8000` plus a Next.js frontend at `:3000`. The
agent-driveable surface is the API. Drive it with the committed driver
**`.claude/skills/run-law-ai/driver.sh`**, which launches daphne in a throwaway
container (SQLite, no heavy deps) and curl-smokes the public endpoints. All paths
below are relative to the repo root.

> Everything runs inside Docker via `docker compose` / `make` — never `pytest`,
> `pip`, `python manage.py`, etc. on the host (see [CLAUDE.md](CLAUDE.md)).

## Prerequisites

On the host: `docker` + `docker compose` v2, plus `curl`, `python3`, and `make`
(used by the driver and the agent demos). No host-level Python/Node setup — the
backend image carries all app dependencies. The image auto-builds on the first
`docker compose run` (a few minutes); to pre-build explicitly:

```bash
docker compose build backend
```

## Run (agent path) — the driver

```bash
bash .claude/skills/run-law-ai/driver.sh
```

Launches the API (daphne + SQLite + `--no-deps`, telemetry and the Claude Code
provider forced off for determinism), waits for `/health`, then smoke-tests the
public surface and tears down. Verified output:

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
docker rm -f law_ai-api                           # stop it
```

The API is **default-open** in dev (no `*_API_KEY` set), so curl needs no auth.
`POST /api/analysis` runs the `LegalAnalyst` IRAC agent through the HTTP layer.

## Drive the agents with a real LLM (optional)

These `make` targets run agents through their full pipeline. They use the
**dev-only Claude Code OAuth provider** when opted in (`LSAT_LLM_PROVIDER=claude_code`
+ `CLAUDE_CODE_OAUTH_TOKEN` in `backend/.env`, see
[docs/claude-code-dev-llm.md](docs/claude-code-dev-llm.md)); otherwise they fall
back to Ollama / a deterministic offline draft, so they still run on a clean clone.

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

`make dev` brings up the **entire** stack (postgres, neo4j, redis, ollama,
phoenix, backend, frontend) and serves the Next.js GUI. It is heavy and was **not**
exercised by this headless harness — use the driver above to confirm the API
boots; use `make dev` when you actually need the browser UI or the graph/ingestion
features (which need Neo4j/Ollama).

## Test

The backend suite runs in a container. For an isolated run that doesn't need the
compose Postgres, override `DATABASE_URL` to SQLite (verified form):

```bash
docker compose run --rm --no-deps \
  -e DATABASE_URL=sqlite:///./test.sqlite3 -e PHOENIX_COLLECTOR_ENDPOINT= \
  backend pytest tests/api/test_lsat.py --no-header --no-cov -p no:cacheprovider -q
```

`make test-backend` runs the full suite but assumes the stack's Postgres is up.
Single test: append `tests/path::test_name`. Lint/type: `make lint` / `make typecheck`.

## Gotchas

- **`docker compose run` starts ALL deps unless you pass `--no-deps`.** Without
  it, postgres/neo4j/redis/**ollama** all spin up (slow, and they linger after).
  The driver uses `--no-deps`; the API needs none of them for the endpoints above.
- **The compose `backend` service injects `DATABASE_URL=postgres://…@postgres`,**
  which overrides the settings' SQLite test default (env wins over `.env`). A bare
  `docker compose run backend pytest …` then fails with *"failed to resolve host
  'postgres'"*. Pass `-e DATABASE_URL=sqlite:///./x.sqlite3` for a Postgres-free run.
- **Don't use the Dockerfile `CMD` verbatim for a light run** — it runs
  `ensure_checkpointer`, which needs Postgres. The driver runs only
  `migrate --noinput && daphne …`, which is fine on SQLite.
- **Phoenix/OpenTelemetry spams `Failed to resolve 'phoenix'`** when the stack
  isn't up. Set `-e PHOENIX_COLLECTOR_ENDPOINT=` (the driver does) to silence it —
  it's noise, not an error.
- **`DJANGO_SETTINGS_MODULE` defaults to `law_ai.settings.dev`** (DEBUG=True) via
  `manage.py`/`asgi.py`. That's what makes the dev-only Claude Code gate eligible.
- **macOS hosts have no `timeout`** — don't wrap commands in it; rely on the
  tool/shell timeout instead.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to resolve host 'postgres'` | Add `-e DATABASE_URL=sqlite:///./run.sqlite3` (no Postgres needed for the API/LSAT routes). |
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | `docker rm -f law_ai-api`, or run the driver with `PORT=8001`. |
| Driver hangs at "waiting for /health" | `docker logs law_ai-api` — usually a missing `-e DATABASE_URL` override or a migrate error. |
| Endless `Failed to resolve 'phoenix'` lines | Set `-e PHOENIX_COLLECTOR_ENDPOINT=`. |
| Agent demo says `via mock / fallback` | Expected without an LLM. For live runs, set `LSAT_LLM_PROVIDER=claude_code` + `CLAUDE_CODE_OAUTH_TOKEN` in `backend/.env` (dev only), or have Ollama running. |
