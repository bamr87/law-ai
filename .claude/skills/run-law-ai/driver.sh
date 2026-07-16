#!/usr/bin/env bash
# Driver for the Law AI backend API.
#
# Launches the Django/daphne ASGI app in a throwaway Docker container
# (SQLite, --no-deps, telemetry off, deterministic offline LLM), smoke-tests
# the public HTTP surface, then tears down. This is the agent-facing way to
# confirm the app boots and serves — no Postgres/Neo4j/Redis/Ollama needed.
#
# Run from the repo root:   bash .claude/skills/run-law-ai/driver.sh
# Keep it running for poking: KEEP=1 bash .claude/skills/run-law-ai/driver.sh
#
# Requires: docker + docker compose, python3, curl. The backend image builds
# on first run (a few minutes); subsequent runs reuse it.
set -uo pipefail

NAME=law_ai-api
PORT=${PORT:-8000}
B="http://localhost:${PORT}"
KEEP=${KEEP:-0}

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
[ "$KEEP" = 1 ] || trap cleanup EXIT
cleanup  # remove any stale container from a previous run

echo "[driver] launching backend API (daphne, sqlite, --no-deps) on :${PORT}…"
docker compose run --rm --no-deps -d -p "${PORT}:8000" --name "$NAME" \
  -e DATABASE_URL=sqlite:///./run.sqlite3 \
  -e PHOENIX_COLLECTOR_ENDPOINT= \
  -e LSAT_LLM_PROVIDER=ollama \
  -e CLAUDE_CODE_OAUTH_TOKEN= \
  backend sh -c \
  "python manage.py migrate --noinput && daphne -b 0.0.0.0 -p 8000 law_ai.asgi:application" \
  >/dev/null || { echo "[driver] FAIL: could not start container"; exit 1; }

echo "[driver] waiting for /health (migrate + bind)…"
if ! curl -fsS --retry 60 --retry-connrefused --retry-delay 2 --retry-all-errors \
     "$B/health" >/dev/null 2>&1; then
  echo "[driver] FAIL: API never became ready. Last logs:"
  docker logs "$NAME" 2>&1 | tail -30
  exit 1
fi
echo "[driver] API is up."

fail=0
check() { # METHOD PATH EXPECTED [JSON_BODY]
  local m=$1 p=$2 exp=$3 data=${4:-}
  local args=(-s -o /dev/null -w '%{http_code}' -X "$m" "$B$p")
  [ -n "$data" ] && args+=(-H 'Content-Type: application/json' -d "$data")
  local got; got=$(curl "${args[@]}")
  if [ "$got" = "$exp" ]; then
    printf "  PASS  %-5s %-34s %s\n" "$m" "$p" "$got"
  else
    printf "  FAIL  %-5s %-34s got %s want %s\n" "$m" "$p" "$got" "$exp"; fail=1
  fi
}

echo "[driver] smoke (status codes):"
check GET  /health                         200
check GET  /api/lsat/sections              200
check GET  "/api/lsat/questions?limit=2"   200
check GET  /api/agents                     200
check GET  /api/agents/health/local-ai     200
check GET  /api/analysis                   405   # POST-only endpoint exists
check POST /api/analysis                   200 '{"text":"Is leaving a wet floor unmarked negligence?"}'

# Functional flow: grade + tutor a real bank question end-to-end.
QID=$(curl -s "$B/api/lsat/questions?limit=1" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['questions'][0]['id'])")
echo "[driver] using bank question: ${QID}"
check POST /api/lsat/grade                 200 "{\"question_id\":\"$QID\",\"choice\":\"A\"}"
check POST /api/lsat/tutor                 200 "{\"question_id\":\"$QID\"}"

echo "[driver] sample bodies:"
curl -s "$B/api/lsat/sections" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  sections:',[s['code'] for s in d['sections']])"
curl -s "$B/api/agents" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  agents:  ',[a['name'] for a in d['agents']])"
curl -s -X POST "$B/api/lsat/tutor" -H 'Content-Type: application/json' -d "{\"question_id\":\"$QID\"}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  tutor:    used_llm=%s model=%s' % (d['used_llm'], d['model']))"

echo ""
if [ "$fail" = 0 ]; then echo "[driver] ✅ ALL CHECKS PASSED"; else echo "[driver] ❌ SOME CHECKS FAILED"; fi
if [ "$KEEP" = 1 ]; then
  echo "[driver] KEEP=1 — API still running at $B (stop: docker rm -f $NAME)"
fi
exit $fail
