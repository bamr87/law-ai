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
# Include the Next.js GUI:    FRONTEND=1 bash .claude/skills/run-law-ai/driver.sh
#
# FRONTEND=1 additionally starts the compose `frontend` service on :3000,
# pointed at this driver's API container, and smoke-tests the rendered pages
# (BL-20260615-04). It is off by default because the Next dev server adds a
# minute of first-compile time that an API-only check does not need.
#
# Requires: docker + docker compose, python3, curl. The backend image builds
# on first run (a few minutes); subsequent runs reuse it.
set -uo pipefail

# Container names are hyphen-only on purpose: with FRONTEND=1 the Next server
# reaches this container by name, and Django's host_validation_re rejects a
# Host header containing an underscore ("DisallowedHost") no matter what
# ALLOWED_HOSTS says. `law_ai-api` produced a 400 on every proxied call.
NAME=law-ai-driver-api
PORT=${PORT:-8000}
B="http://localhost:${PORT}"
KEEP=${KEEP:-0}
FRONTEND=${FRONTEND:-0}
FNAME=law-ai-driver-web
FPORT=${FPORT:-3000}
W="http://localhost:${FPORT}"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker rm -f "$FNAME" >/dev/null 2>&1 || true
}
[ "$KEEP" = 1 ] || trap cleanup EXIT
cleanup  # remove any stale containers from a previous run

echo "[driver] launching backend API (daphne, sqlite, --no-deps) on :${PORT}…"
docker compose run --rm --no-deps -d -p "${PORT}:8000" --name "$NAME" \
  -e DATABASE_URL=sqlite:///./run.sqlite3 \
  -e PHOENIX_COLLECTOR_ENDPOINT= \
  -e LLM_PROVIDER_CHAIN=ollama \
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

# ---------------------------------------------------------------------------
# Optional GUI smoke (FRONTEND=1) — BL-20260615-04.
#
# The Next dev server talks to the backend server-side through
# BACKEND_INTERNAL_URL, so it is pointed at this driver's API *container*
# (compose puts both on the project network, addressable by --name), not at
# localhost — localhost inside the frontend container is the frontend.
# HOSTNAME=0.0.0.0 makes Next bind all interfaces so the published port is
# reachable from the host.
# ---------------------------------------------------------------------------
if [ "$FRONTEND" = 1 ]; then
  echo ""
  echo "[driver] launching Next.js GUI (--no-deps) on :${FPORT}…"
  docker compose run --rm --no-deps -d -p "${FPORT}:3000" --name "$FNAME" \
    -e HOSTNAME=0.0.0.0 \
    -e BACKEND_INTERNAL_URL="http://${NAME}:8000" \
    -e NEXT_PUBLIC_API_URL="http://localhost:${PORT}" \
    -e NEXT_PUBLIC_WS_URL="ws://localhost:${PORT}" \
    -e NEXT_PUBLIC_API_BASE_URL=/api/backend \
    frontend npm run dev \
    >/dev/null || { echo "[driver] FAIL: could not start frontend container"; exit 1; }

  echo "[driver] waiting for the dev server to compile (first boot is slow)…"
  if ! curl -fsS --retry 90 --retry-connrefused --retry-delay 2 --retry-all-errors \
       "$W/" >/dev/null 2>&1; then
    echo "[driver] FAIL: GUI never became ready. Last logs:"
    docker logs "$FNAME" 2>&1 | tail -30
    fail=1
  else
    echo "[driver] GUI is up."

    page() { # PATH MARKER — 200 plus a string that proves the route rendered
      local p=$1 marker=$2 body code
      body=$(curl -s -w '\n%{http_code}' "$W$p")
      code=${body##*$'\n'}
      body=${body%$'\n'*}
      if [ "$code" = "200" ] && printf '%s' "$body" | grep -qi -- "$marker"; then
        printf "  PASS  %-24s 200, matched %s\n" "$p" "$marker"
      else
        printf "  FAIL  %-24s code=%s marker=%s not found\n" "$p" "$code" "$marker"
        fail=1
      fi
    }

    # Warm each route first. Next dev compiles per route on demand and answers
    # 200 with a shell while it is still building, so asserting on the first
    # response makes this check flaky (`/` failed exactly once that way).
    for p in / /lsat /analysis; do curl -s -o /dev/null "$W$p"; done

    echo "[driver] GUI smoke (status + rendered marker):"
    page /          "Law AI"
    page /lsat      "LSAT"
    page /analysis  "analysis"

    # Proves the browser→Next→backend proxy hop, not just that Next renders:
    # this route is served by the Next server and forwards to the API container.
    check_proxy=$(curl -s -o /dev/null -w '%{http_code}' "$W/api/backend/api/lsat/sections")
    if [ "$check_proxy" = "200" ]; then
      printf "  PASS  %-24s 200 (Next → %s)\n" "/api/backend/…/sections" "$NAME"
    else
      printf "  FAIL  %-24s got %s want 200\n" "/api/backend/…/sections" "$check_proxy"
      fail=1
    fi
  fi
fi

echo ""
if [ "$fail" = 0 ]; then echo "[driver] ✅ ALL CHECKS PASSED"; else echo "[driver] ❌ SOME CHECKS FAILED"; fi
if [ "$KEEP" = 1 ]; then
  echo "[driver] KEEP=1 — API still running at $B (stop: docker rm -f $NAME)"
  [ "$FRONTEND" = 1 ] && echo "[driver] KEEP=1 — GUI still running at $W (stop: docker rm -f $FNAME)"
fi
exit $fail
