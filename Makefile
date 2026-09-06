.PHONY: help setup dev down logs ps debug debug-frontend shell-backend shell-frontend manage \
	test test-backend test-frontend test-lsat-static test-coverage test-smoke test-specs \
	test-integration test-integration-ollama test-e2e test-e2e-typecheck test-e2e-down \
	test-legalbench test-legalbench-gate legalbench-cache legalbench-baseline \
	lint format typecheck mypy-baseline migrate ingest densify-backfill backfill-embeddings \
	evolve-audit lint-specs ux-audit ui-sync nightly-dry-run \
	autonomy-run autonomy-status autonomy-stop \
	local-ai-up local-ai-down local-ai-pull local-ai-verify local-ai-health validate-claude-code \
	xai-login validate-xai studio-up studio-down \
	local-ai-up-gpu local-ai-down-gpu dev-gpu logs-gpu vllm-up vllm-down \
	local-ai-bundle local-ai-offline-install \
	observability-up observability-down local-ai-up-server local-ai-down-server \
	lsat-author-demo lsat-export lsat-guide-backfill lsat-static-build lsat-static-e2e \
	lsat-library-audit lsat-library-review \
	lsat-synth-list lsat-synth-preview lsat-synth-generate lsat-synth-sweep \
	lsat-synth-polish-yield lsat-synth-calibrate lsat-cross-check-sweep \
	legal-analyst-demo host-setup host-test reset-db clean

# =============================================================================
# Docker is the canonical dev/test surface. Every target below shells into
# `docker compose run --rm <service>` so you never need a local Python/Node
# toolchain. Host-only targets are marked `host-*` and are kept for emergency
# fallback only.
# =============================================================================

DC               := docker compose
RUN_BACKEND      := $(DC) run --rm --no-deps backend
RUN_WORKER       := $(DC) run --rm --no-deps worker
RUN_FRONTEND     := $(DC) run --rm --no-deps frontend
# For tests/integration that need real DBs, drop --no-deps so depends_on
# brings postgres/neo4j/redis up.
RUN_BACKEND_FULL := $(DC) run --rm backend

help:
	@echo "Law AI — Docker-first development"
	@echo ""
	@echo "Stack:"
	@echo "  make dev               - Start full stack (foreground, builds images)"
	@echo "  make down              - Stop and remove containers"
	@echo "  make logs              - Tail logs from all services"
	@echo "  make ps                - List running services"
	@echo "  make debug             - Start stack with debugpy/inspect attach ports"
	@echo "  make debug-frontend    - Build/start debug stack detached until frontend is healthy"
	@echo ""
	@echo "Shells / one-offs (in containers):"
	@echo "  make shell-backend     - Bash shell in the backend container"
	@echo "  make shell-frontend    - Sh shell in the frontend container"
	@echo "  make manage CMD='...'  - Run Django manage.py inside backend container"
	@echo "  make migrate           - Run Django + Neo4j migrations + ensure_checkpointer"
	@echo "  make ingest            - Run scripts/ingest_sample.py"
	@echo "  make densify-backfill  - Re-resolve historical citations into :CITES edges (COMMIT=1 to write)"
	@echo "  make backfill-embeddings - Embed historical :Case/:StatuteSection nodes locally (COMMIT=1 to write)"
	@echo ""
	@echo "Tests (all run in containers):"
	@echo "  make test              - Backend pytest + frontend vitest"
	@echo "  make test-backend      - Backend pytest (all unit tests, excludes integration+legalbench)"
	@echo "  make test-frontend     - Frontend vitest"
	@echo "  make test-lsat-static  - Static LSAT site vitest (node container, no compose service)"
	@echo "  make test-coverage     - Coverage reports for backend + frontend"
	@echo "  make test-smoke        - Repo-wide smoke + spec/backlog lint"
	@echo "  make test-specs        - Spec validator + backlog lint"
	@echo "  make test-integration  - Integration tests against real Neo4j/Postgres"
	@echo "  make test-integration-ollama - Factory run against the local Ollama model"
	@echo "  make test-e2e          - Browser end-to-end against the live stack (nightly; docs/e2e-testing.md)"
	@echo "  make test-legalbench   - LegalBench eval"
	@echo "  make legalbench-cache  - Download the real LegalBench data (pinned revision) into backend/var/legalbench/"
	@echo ""
	@echo "Quality:"
	@echo "  make lint              - ruff + black + frontend lint --fix (in containers)"
	@echo "  make format            - black + ruff fix + prettier (in containers)"
	@echo "  make typecheck         - mypy --strict (ratcheted) + tsc --noEmit (in containers)"
	@echo "  make mypy-baseline     - re-bank backend/mypy-baseline.txt after a burn-down"
	@echo "  make lint-specs        - spec drift + BACKLOG + UI/UX contract (host stdlib)"
	@echo "  make nightly-dry-run   - smoke-test nightly-tests.yml locally via nektos/act (dry_run path)"
	@echo "  make ux-audit          - UI/UX contract, both front ends (docs/ui-ux-review.md)"
	@echo "  make ui-sync           - mirror the shared UI/keyboard/timer primitives into lsat-static"
	@echo "  make lsat-static-build - build the static LSAT site in a container (as Pages does)"
	@echo "  make lsat-static-e2e   - viewport/sticky measurements over the built export (real browser)"
	@echo ""
	@echo "Local AI stack (Spec 010):"
	@echo "  make local-ai-up       - Start postgres/redis/neo4j/ollama/phoenix"
	@echo "  make local-ai-down     - Stop the above"
	@echo "  make local-ai-pull     - Pull default Ollama models"
	@echo "  make local-ai-health   - Hit /api/agents/health/local-ai"
	@echo "  make local-ai-up-gpu   - Workstation tier: Ollama on NVIDIA GPUs, 70B default (docker-compose.gpu.yml)"
	@echo "  make dev-gpu           - Full stack on the GPU overlay"
	@echo "  make vllm-up           - Optional vLLM server on :8001 (GPU overlay, profile vllm)"
	@echo "  make local-ai-bundle   - Build the air-gapped bundle (models + images) into dist/"
	@echo "  make local-ai-offline-install - Restore a bundle on a disconnected host"
	@echo "  make observability-up  - Prometheus :9090 + Grafana :3002 (queue depth; GPU panels need the server tier)"
	@echo "  make local-ai-up-server - Server tier: GPU + vLLM + Prometheus/Grafana/DCGM"
	@echo "  make validate-claude-code - Validate the dev-time Claude Code OAuth integration (LSAT)"
	@echo "  make xai-login       - Authorise the xAI Grok tier (subscription OAuth, device code)"
	@echo "  make validate-xai    - Validate the xAI Grok tier end-to-end"
	@echo "  make studio-up         - LangGraph Studio host for LegalWorkflow (needs LANGSMITH_API_KEY; docs/local-ai.md)"
	@echo "  make studio-down       - Stop the Studio host"
	@echo "  make lsat-author-demo  - Run the LSATContentAuthor agent live (via Claude Code when opted in)"
	@echo "  make lsat-guide-backfill - Draft solve guides for guide-less questions into the HITL queue"
	@echo "  make lsat-library-audit  - Deterministic knowledge-library health report (no LLM)"
	@echo "  make lsat-cross-check-sweep - Blind-solve unchecked questions; disagreements to the HITL queue"
	@echo "  make lsat-library-review - HITL-gated LSATLibrarian review pass over the library"
	@echo "  make lsat-synth-list     - Schemas and domain packs the synthesis engine ships"
	@echo "  make lsat-synth-sweep    - Generate across every schema x domain and verify each"
	@echo "  make lsat-synth-polish-yield - Measure the polish prompt's yield (calls the provider chain)"
	@echo "  make lsat-synth-calibrate - Measured vs declared difficulty per schema"
	@echo "  make legal-analyst-demo - Run the LegalAnalyst IRAC agent live (via Claude Code when opted in)"
	@echo ""
	@echo "Autonomy (Spec 018 — requires AUTONOMY_ENABLED=true):"
	@echo "  make autonomy-run KIND=corpus_growth SOURCE=courtlistener  - one cycle (also accepts AUTONOMY_KIND/SOURCE)"
	@echo "  make autonomy-run KIND=test_pillar BUDGET=10               - pillar A"
	@echo "  make autonomy-status                                       - show beat schedule"
	@echo "  make autonomy-stop                                         - stop consuming from autonomy queue (does NOT purge)"
	@echo ""
	@echo "Misc:"
	@echo "  make reset-db          - DESTRUCTIVE: drop ONLY the Postgres volume (see the major-version pin in docker-compose.yml), then 'make dev && make migrate'"
	@echo "  make clean             - 'docker compose down -v' + clear caches"
	@echo "  make host-setup        - LEGACY: pip install + npm install on host"
	@echo "  make host-test         - LEGACY: run tests on host (no Docker)"

# ---------------------------------------------------------------------------
# Stack lifecycle
# ---------------------------------------------------------------------------

setup:
	$(DC) build

dev:
	$(DC) up --build

down:
	$(DC) down

logs:
	$(DC) logs -f

ps:
	$(DC) ps

debug:
	$(DC) -f docker-compose.yml -f docker-compose.debug.yml up --build

debug-frontend:
	$(DC) -f docker-compose.yml -f docker-compose.debug.yml up --build -d --wait --wait-timeout 180 frontend

# ---------------------------------------------------------------------------
# Shells / one-offs (always in containers)
# ---------------------------------------------------------------------------

shell-backend:
	$(RUN_BACKEND) bash

shell-frontend:
	$(RUN_FRONTEND) sh

manage:
	@if [ -z "$(CMD)" ]; then echo "Usage: make manage CMD='migrate'"; exit 1; fi
	$(RUN_BACKEND_FULL) python manage.py $(CMD)

migrate:
	$(RUN_BACKEND_FULL) sh -c "python manage.py migrate && python manage.py migrate_neo4j && python manage.py ensure_checkpointer"

ingest:
	$(RUN_BACKEND_FULL) python scripts/ingest_sample.py --source courtlistener --limit 500

# Re-run citation densification over historical :Case nodes (BL-20260429-11).
# Read-only by default; pass COMMIT=1 to actually MERGE the :CITES edges.
densify-backfill:
	$(RUN_BACKEND_FULL) python manage.py densify_backfill $(if $(COMMIT),--commit,) $(if $(LIMIT),--limit $(LIMIT),)

# Fill `embedding` on :Case / :StatuteSection so the GraphRAG vector leg can
# see the historical corpus (BL-20260810-17). Local (Ollama) only.
backfill-embeddings:
	$(RUN_BACKEND_FULL) python manage.py backfill_embeddings $(if $(COMMIT),--commit,) $(if $(LIMIT),--limit $(LIMIT),)

# ---------------------------------------------------------------------------
# Tests (Docker-only)
# ---------------------------------------------------------------------------

test: test-backend test-frontend test-lsat-static

test-backend:
	$(RUN_BACKEND) pytest -m "not integration and not legalbench" -q --tb=short

test-frontend:
	$(RUN_FRONTEND) npm test -- --run

# Component tests for the static LSAT site (BL-20260831-18). Same container
# pattern as lsat-static-build — `lsat-static/` has no compose service — but
# node_modules lives on a named volume so the Linux install never lands in
# the host checkout and a host `npm install` never breaks the container.
test-lsat-static:
	docker run --rm -v "$(PWD)":/repo \
		-v law_ai_lsat_static_node_modules:/repo/lsat-static/node_modules \
		-w /repo/lsat-static node:20-alpine \
		sh -c "npm ci --no-audit --no-fund && npm test -- --run"

test-coverage:
	$(RUN_BACKEND) pytest --cov=law_ai --cov-report=xml --cov-report=html --cov-report=term
	$(RUN_FRONTEND) npm run test:coverage

test-smoke:
	$(RUN_BACKEND) pytest -m "not integration and not legalbench"

test-specs:
	python3 scripts/spec_validator.py
	python3 scripts/backlog_lint.py

test-integration:
	$(DC) up -d neo4j postgres redis --wait
	@trap '$(DC) stop neo4j postgres redis' EXIT INT TERM; \
	  $(DC) run --rm \
	    -e DATABASE_URL=postgresql://law_ai:law_ai-dev@postgres:5432/law_ai \
	    -e NEO4J_URI=bolt://neo4j:7687 \
	    -e NEO4J_USER=neo4j \
	    -e NEO4J_PASSWORD=law_ai-dev \
	    -e REDIS_URL=redis://redis:6379/0 \
	    backend pytest -m integration -v --no-cov
# --no-cov: the integration subset is a targeted slice, so the repo-wide
# --cov-fail-under=75 in pyproject addopts would always fail it (~35% here)
# even when every test passes. Coverage is measured by `make test-backend`.

# Integration against the LOCAL MODEL (BL-20260702-05, BL-20260527-08). Split
# out from test-integration so the DB-only run is not slowed by an ollama model
# pull: this one boots ollama too and points the suite at it, then runs the
# factory slice (`lsat_factory run --executor ollama`) and the autonomy →
# HITL loop (`run_autonomy --kind lsat_content` then an approve through the
# API) end to end. Both tests pin LLM_PROVIDER_CHAIN to ollama so no hosted
# tier is ever billed, and both skip themselves when the model is not pulled,
# so an ollama-less box still passes.
# OLLAMA_INTEGRATION_MODEL overrides the model BOTH tests generate with — the
# compose default is a 7B that needs ~5 GiB resident, which a laptop Docker VM
# often cannot spare; point it at a smaller pulled model
# (e.g. `make test-integration-ollama OLLAMA_INTEGRATION_MODEL=qwen2.5:3b-instruct-q4_K_M`)
# rather than let the tests skip forever. Both refuse to pass against a dead
# model: the autonomy test asserts the cycle was not degraded and that an
# `llm_call` succeeded on the ollama tier (BL-20260527-08), because the author
# files fallback drafts and the router logs an llm_call even on total failure.
test-integration-ollama:
	$(DC) up -d ollama postgres redis --wait
	@trap '$(DC) stop ollama postgres redis' EXIT INT TERM; \
	  $(DC) run --rm \
	    -e DATABASE_URL=postgresql://law_ai:law_ai-dev@postgres:5432/law_ai \
	    -e REDIS_URL=redis://redis:6379/0 \
	    -e OLLAMA_INTEGRATION_URL=http://ollama:11434 \
	    -e OLLAMA_INTEGRATION_MODEL=$(OLLAMA_INTEGRATION_MODEL) \
	    backend pytest tests/lsat/test_factory_ollama_integration.py \
	    tests/core/test_run_autonomy_integration.py \
	    -m integration -v --no-cov

# Live-network drift smoke (BL-20260511-07). One real Justia fetch, re-run
# through the parser, so upstream HTML drift surfaces before an ingestion run
# silently returns zero sections. Nightly + on demand only: it is the single
# target in this repo that touches a third-party site, and it is gated behind
# LIVE_NETWORK=1. A blocked or unreachable upstream *skips* (no drift signal is
# available), so the nightly step needs no `continue-on-error`: a red run here
# means Justia answered and the parse came back wrong. One request per run — do
# not loop titles; Justia's crawl-delay is why rate_limit_rps is 0.5.
test-live-network:
	$(RUN_BACKEND) sh -c "LIVE_NETWORK=1 pytest -m network -v --no-cov"

# ---------------------------------------------------------------------------
# Browser end-to-end (spec 051 / BL-20260811-16). Deliberately NOT part of
# `make test`: it boots the whole stack plus a browser image, so it runs
# nightly and on demand. Both services live behind the compose `e2e` profile,
# so `make dev` / `make down` never see them.
#
# `backend-e2e` is a second API pinned to an unreachable Ollama, so every run
# takes the deterministic degraded path and bills nobody. The browser reaches
# the stack over localhost via frontend/e2e/proxy.mjs.
#
# The frontend is RECREATED pointing at that sidecar. Since BL-20260430-07 the
# browser's REST calls go through the Next same-origin proxy, so whatever
# BACKEND_INTERNAL_URL names is the API the UI actually talks to — leaving it
# at the dev backend would route e2e analysis runs through the operator's real
# provider chain and bill them. AGENT_API_KEY is the server-side key that proxy
# attaches; it tracks E2E_AGENT_API_KEY so the gated project sees a coherent
# stack. `make dev` restores the defaults on its next `up`.
#
#   make test-e2e                     # whole suite
#   make test-e2e E2E_ARGS='e2e/a11y.spec.ts --headed=0'
#   make test-e2e E2E_AGENT_API_KEY=s3cret   # gate the API for the auth spec
# ---------------------------------------------------------------------------
E2E_ARGS ?=
E2E_AGENT_API_KEY ?=
# Set to 1 to re-record frontend/e2e/a11y-baseline.json rather than assert
# against it (a11y.spec.ts documents when that is the right move).
E2E_A11Y_UPDATE_BASELINE ?=

test-e2e:
	FRONTEND_BACKEND_URL=http://backend-e2e:8000 \
	  AGENT_API_KEY=$(E2E_AGENT_API_KEY) \
	  E2E_AGENT_API_KEY=$(E2E_AGENT_API_KEY) \
	  $(DC) --profile e2e up -d --wait frontend backend-e2e
	# The admin HITL spec approves a known quarantine row; --reset puts it back
	# in the pending state so the suite is re-runnable without a DB wipe.
	$(DC) --profile e2e exec -T backend-e2e python manage.py seed_review_queue --reset
	# The analysis spec needs a *healthy* result to render (the sidecar's
	# unreachable Ollama can only produce the degraded panel) and the auth spec
	# needs an /analysis page visit that provokes a gated API call. One
	# persisted run, replayed at /analysis?id=…, is both.
	$(DC) --profile e2e exec -T backend-e2e python manage.py seed_analysis_run
	E2E_AGENT_API_KEY=$(E2E_AGENT_API_KEY) \
	  E2E_A11Y_UPDATE_BASELINE=$(E2E_A11Y_UPDATE_BASELINE) \
	  $(DC) --profile e2e run --rm --no-deps e2e npx playwright test $(E2E_ARGS)

# Put the frontend back on the dev backend after a `make test-e2e` run.
test-e2e-down:
	$(DC) --profile e2e stop backend-e2e e2e
	$(DC) up -d --wait frontend

# Type-checks the specs against the Playwright/axe types, which only exist in
# the e2e image — the app's own `tsc --noEmit` excludes frontend/e2e.
test-e2e-typecheck:
	$(DC) --profile e2e run --rm --no-deps e2e npx tsc -p e2e/tsconfig.json


test-legalbench:
	$(RUN_BACKEND_FULL) python -m law_ai.eval.legalbench --subset core_reasoning,precedent_retrieval

# CI form: fails the build when a listed subset drops more than 1 pp against
# backend/var/legalbench/baseline.json (constitution §3). Exit codes are
# distinct — 1 = regression, 2 = the eval could not run (Ollama down / model
# not pulled), so a broken stack is never reported as a model regression.
# --fail-on-synthetic (BL-20260811-10) is what stops a stub-backed run from
# satisfying the gate: with no cached dataset the harness scores five smoke
# fixtures, "passes", and reports nothing. Run `make legalbench-cache` first —
# nightly does, in the step above the gate.
test-legalbench-gate:
	$(RUN_BACKEND_FULL) python -m law_ai.eval.legalbench \
		--subset core_reasoning,precedent_retrieval \
		--check-regression --fail-on-synthetic

# Download the real LegalBench task data at the revisions pinned in
# law_ai/eval/fetch.py and cache it as backend/var/legalbench/<subset>/items.jsonl
# (BL-20260811-09). Needs outbound network; the items are never vendored, so
# every runner that evaluates must run this first. LEGALBENCH_SUBSETS overrides
# which subsets are cached; MANIFEST=update accepts changed source checksums.
LEGALBENCH_SUBSETS ?= core_reasoning,precedent_retrieval
legalbench-cache:
	$(RUN_BACKEND) python -m law_ai.eval.fetch --subset $(LEGALBENCH_SUBSETS) \
		$(if $(filter update,$(MANIFEST)),--update-manifest,)

# Record the current accuracies as the tracked baseline. Refuses to run
# against synthetic stub fixtures — cache a real dataset first.
legalbench-baseline:
	$(RUN_BACKEND_FULL) python -m law_ai.eval.legalbench \
		--subset core_reasoning,precedent_retrieval --update-baseline

# ---------------------------------------------------------------------------
# Quality (Docker-only)
# ---------------------------------------------------------------------------

lint:
	$(RUN_BACKEND) sh -c "ruff check --fix . && black ."
	$(RUN_FRONTEND) npm run lint -- --fix

format:
	$(RUN_BACKEND) sh -c "black . && ruff check --fix ."
	$(RUN_FRONTEND) npx prettier --write .

# BL-20260429-04: the backend half is `mypy law_ai --strict` behind the ratchet
# in scripts/mypy_ratchet.py — it fails when a file's strict-error count grows
# or a file the baseline calls clean stops being clean, so the gate is real
# without requiring the whole tree to be strict-clean first. Same command as
# CI's backend-lint job. The frontend half is already clean, so it is bare.
typecheck:
	$(RUN_BACKEND) python3 /repo/scripts/mypy_ratchet.py --run
	$(RUN_FRONTEND) npx tsc --noEmit

# Bank the current strict-error counts into backend/mypy-baseline.txt. Run
# after burning a file down; review the diff — the totals should only fall.
mypy-baseline:
	$(RUN_BACKEND) python3 /repo/scripts/mypy_ratchet.py --run --update

# ---------------------------------------------------------------------------
# Spec/backlog/UX validators (lightweight — host only, no container)
# ---------------------------------------------------------------------------

lint-specs:
	python3 scripts/spec_validator.py
	python3 scripts/backlog_lint.py
	python3 scripts/ux_audit.py
	@# BL-20260511-14: scripts/evolve_audit.py is the fourth validator in this
	@# family, and its coverage/LegalBench scanners are exercised by
	@# tests/test_evolve_audit.py. That file is deliberately dependency-light
	@# (stdlib + pytest, no Django, no Docker) so it can run right here, next
	@# to the three scripts above, instead of only inside CI's repo-structural
	@# job. pytest is the one non-stdlib thing this target needs; say so
	@# plainly rather than dying in a traceback.
	@python3 -c "import pytest" 2>/dev/null || { \
	  echo "lint-specs: this gate now runs tests/test_evolve_audit.py, which needs pytest on the host interpreter."; \
	  echo "            Install it (python3 -m pip install --user pytest) or run the same checks in Docker with 'make test-smoke'."; \
	  exit 1; }
	python3 -m pytest tests/test_evolve_audit.py -q

# The mechanical half of the /ux-review loop. `--list` prints the rules.
ux-audit:
	python3 scripts/ux_audit.py

# Mirror the shared UI primitives into the static export. Next cannot resolve
# a CSS @import outside an app root, so the copy is committed and ux_audit
# R12 fails the build when the two drift.
ui-sync:
	cp frontend/ui/base.css lsat-static/app/base.css
	@echo "frontend/ui/base.css -> lsat-static/app/base.css"
	cp frontend/lib/shell/rovingFocus.ts lsat-static/lib/rovingFocus.ts
	@echo "frontend/lib/shell/rovingFocus.ts -> lsat-static/lib/rovingFocus.ts"
	cp frontend/lib/lsatTimer.ts lsat-static/lib/lsatTimer.ts
	@echo "frontend/lib/lsatTimer.ts -> lsat-static/lib/lsatTimer.ts"
	@mkdir -p lsat-static/lib/lsat
	cp frontend/lib/lsat/timerStore.ts lsat-static/lib/lsat/timerStore.ts
	@echo "frontend/lib/lsat/timerStore.ts -> lsat-static/lib/lsat/timerStore.ts"
	@mkdir -p lsat-static/__tests__/contracts
	cp frontend/__tests__/contracts/solveAssist.contract.ts lsat-static/__tests__/contracts/solveAssist.contract.ts
	@echo "frontend/__tests__/contracts/solveAssist.contract.ts -> lsat-static/__tests__/contracts/solveAssist.contract.ts"


evolve-audit:
	python3 scripts/evolve_audit.py
	$(MAKE) lint-specs

# Smoke-test the nightly workflow locally with nektos/act instead of burning a
# real `gh workflow run nightly-tests.yml -f dry_run=true` dispatch
# (BL-20260511-18). Only the dry_run path is exercised: the Docker-heavy steps
# are guarded by `if: ${{ !inputs.dry_run }}` and the PR step by `!env.ACT`, so
# a local run validates the spec/backlog gates, the stale-backlog reporter and
# the discovery audit without touching the remote. Defaults live in .actrc.
#
# Needs `act` on the host (`brew install act`) — the one sanctioned non-`make`
# host tool, because act *is* the Docker runner. Pass ARGS='-n' to list steps
# without running them.
nightly-dry-run:
	@command -v act >/dev/null 2>&1 || { \
		echo "act is not installed — 'brew install act' (see .actrc)"; exit 1; }
	act workflow_dispatch \
		-W .github/workflows/nightly-tests.yml \
		--input dry_run=true \
		-s GITHUB_TOKEN="$$(gh auth token 2>/dev/null)" $(ARGS)

# ---------------------------------------------------------------------------
# Spec 010: Local AI stack
# ---------------------------------------------------------------------------

local-ai-up:
	$(DC) up -d postgres redis neo4j ollama phoenix
	@echo "Local AI stack starting. Models will pull in background."
	@echo "Phoenix UI:    http://localhost:6006"
	@echo "Ollama tags:   curl localhost:11434/api/tags"

local-ai-down:
	$(DC) stop ollama phoenix postgres redis neo4j

# Pull the model set defined by OLLAMA_BOOTSTRAP_MODELS in the container —
# reading it back rather than restating it here keeps this target and
# ollama-bootstrap.sh from drifting apart (BL-20260810-12).
local-ai-pull:
	$(DC) exec ollama sh -c 'for m in $$OLLAMA_BOOTSTRAP_MODELS; do echo "pulling $$m"; ollama pull "$$m"; done'

# Is the configured gate model actually present? (same check the container
# healthcheck runs)
local-ai-verify:
	$(DC) exec ollama /scripts/ollama-healthcheck.sh && echo "gate model present"

# ---------------------------------------------------------------------------
# Linux + NVIDIA workstation tier (BL-20260502-02). Overlay only — the laptop
# defaults in docker-compose.yml are untouched, so `make dev` and the pinned
# LegalBench model set do not move.
#
# Requires the NVIDIA container toolkit on the host; on a machine without it
# `docker compose ... up` fails with "could not select device driver". First
# boot pulls ~40 GB of 70B weights before Ollama reports healthy.
# ---------------------------------------------------------------------------

DC_GPU := $(DC) -f docker-compose.yml -f docker-compose.gpu.yml

local-ai-up-gpu:
	$(DC_GPU) up -d postgres redis neo4j ollama phoenix
	@echo "GPU tier starting. Default model: $${GPU_OLLAMA_DEFAULT_MODEL:-llama3.1:70b-q4_K_M}"
	@echo "First boot pulls ~40 GB — watch it with: make logs-gpu"

# The whole app on the GPU overlay (what `make dev` is for the laptop tier).
dev-gpu:
	$(DC_GPU) up --build

logs-gpu:
	$(DC_GPU) logs -f ollama

local-ai-down-gpu:
	$(DC_GPU) stop ollama phoenix postgres redis neo4j vllm

# Optional vLLM server (compose profile `vllm`, port 8001, OpenAI-compatible).
# Not a provider-chain tier — benchmarking and manual comparison only.
vllm-up:
	$(DC_GPU) --profile vllm up -d vllm
	@echo "vLLM: http://localhost:8001/v1/models  (metrics at /metrics)"

vllm-down:
	$(DC_GPU) --profile vllm stop vllm

# ---------------------------------------------------------------------------
# Server / multi-GPU tier: Prometheus + Grafana (BL-20260502-03).
#
# `observability-up` runs anywhere (queue depth works on a laptop);
# `local-ai-up-server` adds the GPU overlay, vLLM and the DCGM exporter, which
# need NVIDIA hardware. Dashboards are provisioned from infra/grafana — edit
# the JSON in the repo, not the Grafana UI.
# ---------------------------------------------------------------------------

DC_OBS    := $(DC) -f docker-compose.yml -f docker-compose.observability.yml
DC_SERVER := $(DC) -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.observability.yml

observability-up:
	$(DC_OBS) --profile observability up -d prometheus grafana redis-exporter
	@echo "Prometheus: http://localhost:9090/targets"
	@echo "Grafana:    http://localhost:3002  (admin/admin, dashboard 'Law AI — local inference')"

observability-down:
	$(DC_OBS) --profile observability stop prometheus grafana redis-exporter

# Full server tier: GPU Ollama + vLLM + metrics, including GPU utilization.
local-ai-up-server:
	$(DC_SERVER) --profile observability --profile gpu-metrics --profile vllm \
	  up -d postgres redis neo4j ollama phoenix vllm prometheus grafana redis-exporter dcgm-exporter
	@echo "Prometheus: http://localhost:9090/targets"
	@echo "Grafana:    http://localhost:3002"
	@echo "vLLM:       http://localhost:8001/metrics"

local-ai-down-server:
	$(DC_SERVER) --profile observability --profile gpu-metrics --profile vllm down --remove-orphans

# ---------------------------------------------------------------------------
# Air-gapped deployment (BL-20260502-06). Build the bundle on a CONNECTED
# machine with the stack up and the images built, copy dist/ to the target,
# then run scripts/offline-install.sh there and start with OLLAMA_OFFLINE=1.
# Both scripts drive `docker` itself, so they are host scripts by necessity.
# ---------------------------------------------------------------------------

local-ai-bundle:
	bash scripts/ollama-bundle.sh $(ARGS)

local-ai-offline-install:
	bash scripts/offline-install.sh $(ARGS)

local-ai-health:
	@curl -fsS http://localhost:8000/api/agents/health/local-ai | python3 -m json.tool

# ---------------------------------------------------------------------------
# LangGraph Studio (BL-20260502-01). Self-hosted `langchain/langgraph-api`
# serving the same LegalWorkflow graph the API runs, so a designer can step
# through retrieve → analyze → cite_check node by node.
#
# Requires LANGSMITH_API_KEY in .env (free key; the server validates it against
# beacon.langchain.com at boot) and the visual stepper itself is hosted at
# smith.langchain.com — see "LangGraph Studio" in docs/local-ai.md before you
# turn this on. Dev tool only: it is not a runtime LLM path, and it defaults to
# the local Ollama tier so stepping a graph does not bill a hosted provider.
studio-up:
	@test -n "$${LANGSMITH_API_KEY:-$$(grep -sE '^LANGSMITH_API_KEY=.+' .env)}" || \
	  { echo "LANGSMITH_API_KEY is not set (.env or environment) — the LangGraph server exits at boot without it. See docs/local-ai.md."; exit 1; }
	$(DC) --profile studio up -d --build langgraph-api
	@echo "LangGraph server: http://localhost:2024  (docs at /docs)"
	@echo "Studio UI:        https://smith.langchain.com/studio/?baseUrl=http://localhost:2024"

studio-down:
	$(DC) --profile studio stop langgraph-api langgraph-db-init

validate-claude-code:
	$(RUN_BACKEND_FULL) python manage.py validate_claude_code

# xAI Grok tier (spec 050). Device-code flow by default, which is the one that
# works from inside a container; ARGS='--loopback' is for a host with a browser
# and ARGS='--status' reports the stored credential without changing it.
xai-login:
	$(RUN_BACKEND_FULL) python manage.py xai_login $(ARGS)

validate-xai:
	$(RUN_BACKEND_FULL) python manage.py validate_xai $(ARGS)

# Regenerate the static LSAT practice-site artifact (spec 025): export the
# bank in Docker, then copy it into the committed site directory that GitHub
# Pages deploys.
#
# You do NOT have to remember this any more (BL-20260702-11).
# .github/workflows/refresh-lsat-content.yml re-exports and commits
# content.json for any change under backend/law_ai/lsat/services/data/ — on a
# same-repo pull request it pushes the refresh onto your branch, and on main it
# also dispatches the Pages build. ci.yml's repo-structural job defers the
# drift gate for exactly that case (LSAT_CONTENT_AUTOEXPORT), so a PR no longer
# goes red waiting for you to run this.
#
# Running it yourself is still welcome — the content diff then sits in the same
# commit as the change that caused it — but it is a preference, not a step. The
# gate still enforces on fork PRs, on main, and locally, so keep it green there.
lsat-export:
	$(RUN_BACKEND) python manage.py lsat_export --out var/lsat_site
	cp backend/var/lsat_site/content.json lsat-static/content.json
	@echo "site data refreshed → lsat-static/content.json"

# Draft solve guides for guide-less bank questions (BL-20260831-23). Needs a
# provider (`make claude-login`, ANTHROPIC_API_KEY, or LLM_PROVIDER_CHAIN=
# ollama). Every draft lands in the HITL queue as a pending `guide` proposal —
# nothing reaches a learner until a reviewer approves it on the Authoring tab.
# SECTION (LR|RC|LG) and LIMIT are the budget: run it in batches.
#   make lsat-guide-backfill SECTION=LR LIMIT=20
#   make lsat-guide-backfill ARGS='--dry-run'      # what would be drafted
# Finish a batch with `make lsat-export` so the offline site picks the guides up.
lsat-guide-backfill:
	$(RUN_BACKEND) python manage.py lsat_guide_backfill \
		$(if $(SECTION),--section $(SECTION),) $(if $(LIMIT),--limit $(LIMIT),) $(ARGS)

# Build + typecheck the static LSAT site the way GitHub Pages does, but inside
# a container — Docker-first applies here too, and `lsat-static/` has no
# compose service of its own because nothing in the dev stack serves it.
lsat-static-build:
	docker run --rm -v "$(PWD)":/repo -w /repo/lsat-static \
		-e PAGES_BASE_PATH=/law-ai node:20-alpine \
		sh -c "npm ci --no-audit --no-fund && npm run build"

# Viewport measurements for the built export (spec 051 / BL-20260901-03):
# header heights, 44px touch targets, overflow, sticky passage column. jsdom
# cannot measure any of that, so this drives a real browser over `out/`.
#
# The image tag MUST match @playwright/test in lsat-static/package-lock.json —
# tests/test_e2e_harness.py keeps that lock and the frontend's on one version.
# node_modules lives on the same named volume `make test-lsat-static` uses, so
# the Linux install never lands in the host checkout; the export is built in
# the same container so `out/` is guaranteed to match the code under test.
lsat-static-e2e:
	docker run --rm --ipc=host -v "$(PWD)":/repo \
		-v law_ai_lsat_static_node_modules:/repo/lsat-static/node_modules \
		-w /repo/lsat-static -e PAGES_BASE_PATH=/law-ai -e CI=$(CI) \
		mcr.microsoft.com/playwright:v1.59.1-noble \
		sh -c "npm ci --no-audit --no-fund && npm run build && npx playwright test"

# Live LSATContentAuthor agent run. Routes through the LLM_PROVIDER_CHAIN
# (Claude first; pin `LLM_PROVIDER_CHAIN=ollama` for local-only). Pass extra flags via
# ARGS, e.g. `make lsat-author-demo ARGS='--section RC --difficulty hard'`.
# Spec 048: the knowledge-library maintenance loop. `audit` is deterministic
# and needs no provider; `review` invokes LSATLibrarian and files every result
# as a pending proposal — it never writes under data/library/.
# Spec 049: the deterministic synthesis engine. Every target is offline.
lsat-synth-list:
	$(RUN_BACKEND) python manage.py lsat_synth list

lsat-synth-preview:
	$(RUN_BACKEND) python manage.py lsat_synth preview $(ARGS)

lsat-synth-generate:
	$(RUN_BACKEND) python manage.py lsat_synth generate $(ARGS)

# The engine's regression test: fails on any item that does not verify.
lsat-synth-sweep:
	$(RUN_BACKEND) python manage.py lsat_synth sweep $(ARGS)

# Measure the polish prompt (BL-20260903-17): proposed vs accepted predicates,
# per reject reason and per provider tier, into backend/var/lsat_synth/. This
# is the one synth target that calls the provider chain, so it needs the full
# service (credentials) and costs whatever the answering tier costs.
lsat-synth-polish-yield:
	$(RUN_BACKEND_FULL) python manage.py lsat_synth polish-yield $(ARGS)

# Is the difficulty band telling the truth (BL-20260903-14)? Default reports
# graded accuracy per schema; ARGS='--structural' reports the offline proxy and
# the score cuts the current registry implies. Offline either way.
lsat-synth-calibrate:
	$(RUN_BACKEND) python manage.py lsat_synth_calibrate $(ARGS)

# BL-20260831-21: blind-solve unchecked bank questions and file every
# disagreement into the HITL queue. Calls the provider chain, so it needs the
# full service (credentials); --limit defaults to 5 to cap the spend.
lsat-cross-check-sweep:
	$(RUN_BACKEND_FULL) python manage.py lsat_cross_check_sweep $(ARGS)

lsat-library-audit:
	$(RUN_BACKEND) python manage.py lsat_library audit $(ARGS)

lsat-library-review:
	$(RUN_BACKEND) python manage.py lsat_library review $(ARGS)

lsat-author-demo:
	$(DC) run --rm --no-deps -e PHOENIX_COLLECTOR_ENDPOINT= backend \
		python manage.py run_lsat_author $(ARGS)

# Live LegalAnalyst (IRAC) run — routes through Claude Code when opted in.
legal-analyst-demo:
	$(DC) run --rm --no-deps -e PHOENIX_COLLECTOR_ENDPOINT= backend \
		python manage.py run_legal_analyst $(ARGS)

# ---------------------------------------------------------------------------
# Spec 018 T-009: Autonomy management targets
# ---------------------------------------------------------------------------
# KIND   — cycle kind: test_pillar | corpus_growth | digest  (default: test_pillar)
# SOURCE — source adapter name (corpus_growth only; must be in AUTONOMY_ALLOWED_SOURCES)
# BUDGET — max docs per cycle (optional integer)
# DRY_RUN— set to --dry-run to print without executing

# Accept short-form aliases so `make autonomy-run KIND=corpus_growth` works.
ifdef KIND
AUTONOMY_KIND := $(KIND)
else
AUTONOMY_KIND ?= test_pillar
endif
ifdef SOURCE
AUTONOMY_SOURCE := $(SOURCE)
else
AUTONOMY_SOURCE ?=
endif
ifdef BUDGET
AUTONOMY_BUDGET := $(BUDGET)
else
AUTONOMY_BUDGET ?=
endif
ifdef DRY_RUN
AUTONOMY_DRYRUN := $(DRY_RUN)
else
AUTONOMY_DRYRUN ?=
endif
# Pass-through for run_autonomy flags without a dedicated variable, e.g.
# `make autonomy-run KIND=digest ARGS=--window-to-now` in the nightly
# workflow (BL-20260511-19).
ifdef ARGS
AUTONOMY_ARGS_EXTRA := $(ARGS)
else
AUTONOMY_ARGS_EXTRA ?=
endif

_AUTONOMY_ARGS := --kind $(AUTONOMY_KIND)
ifneq ($(AUTONOMY_SOURCE),)
_AUTONOMY_ARGS += --source $(AUTONOMY_SOURCE)
endif
ifneq ($(AUTONOMY_BUDGET),)
_AUTONOMY_ARGS += --budget $(AUTONOMY_BUDGET)
endif
ifneq ($(AUTONOMY_DRYRUN),)
_AUTONOMY_ARGS += --dry-run
endif
ifneq ($(AUTONOMY_ARGS_EXTRA),)
_AUTONOMY_ARGS += $(AUTONOMY_ARGS_EXTRA)
endif

autonomy-run:
	$(RUN_BACKEND_FULL) python manage.py run_autonomy $(_AUTONOMY_ARGS)

autonomy-status:
	$(RUN_WORKER) celery -A law_ai inspect scheduled

autonomy-stop:
	# Stops the worker from consuming new tasks from the autonomy queue.
	# This does NOT purge tasks already queued — use 'celery purge' for that.
	$(RUN_WORKER) celery -A law_ai control cancel_consumer autonomy

# ---------------------------------------------------------------------------
# Legacy host-based targets (avoid; emergency fallback only)
# ---------------------------------------------------------------------------

host-setup:
	cd backend && pip install -e ".[dev,local-ai,future-auth]"
	cd frontend && npm install

host-test:
	cd backend && pytest -q --cov=law_ai
	cd frontend && npm test -- --run

# DESTRUCTIVE, but narrower than `make clean`: drops ONLY the Postgres volume
# (Django tables + the LangGraph checkpointer schema) and leaves Neo4j, Ollama
# models and Phoenix traces alone. The reason this target exists is the major
# version pin on the `postgres` service in docker-compose.yml — a pg16 data
# directory cannot be read by a pg17+ server, so bumping the tag requires
# wiping the cluster (or a pg_upgrade / dump-restore, see docs/local-ai.md).
# BL-20260503-25.
# COMPOSE_PROJECT is how the volume gets namespaced (`<project>_pgdata`).
# Compose derives it from the directory name unless COMPOSE_PROJECT_NAME is
# set; override on the command line if yours differs. It is filtered on
# deliberately — a bare `--filter name=pgdata` also matches every *other*
# project's pgdata volume on the machine.
COMPOSE_PROJECT ?= $(notdir $(CURDIR))

reset-db:
	@printf 'This DELETES the %s Postgres volume (all local dev DB data). Continue? [y/N] ' "$(COMPOSE_PROJECT)"; \
	read ans; [ "$$ans" = "y" ] || [ "$$ans" = "Y" ] || { echo "aborted"; exit 1; }
	$(DC) stop postgres backend worker
	$(DC) rm -f -v postgres
	@vols=$$(docker volume ls -q \
		--filter label=com.docker.compose.project=$(COMPOSE_PROJECT) \
		--filter name=pgdata); \
	if [ -n "$$vols" ]; then docker volume rm -f $$vols; \
	else echo "no $(COMPOSE_PROJECT) pgdata volume to remove"; fi
	@echo "pgdata removed. Next: 'make dev' (recreates the cluster), then 'make migrate'."

clean:
	$(DC) down -v
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf htmlcov/ .coverage backend/.venv frontend/.next
