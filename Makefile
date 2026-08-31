.PHONY: help setup dev down logs ps debug debug-frontend shell-backend shell-frontend manage \
	test test-backend test-frontend test-coverage test-smoke test-specs \
	test-integration test-legalbench test-legalbench-gate legalbench-baseline \
	lint format typecheck migrate ingest \
	evolve-audit lint-specs \
	autonomy-run autonomy-status autonomy-stop \
	local-ai-up local-ai-down local-ai-pull local-ai-verify local-ai-health validate-claude-code \
	lsat-author-demo lsat-export legal-analyst-demo host-setup host-test clean

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
	@echo "  make migrate           - Run migrations + ensure_checkpointer"
	@echo "  make ingest            - Run scripts/ingest_sample.py"
	@echo ""
	@echo "Tests (all run in containers):"
	@echo "  make test              - Backend pytest + frontend vitest"
	@echo "  make test-backend      - Backend pytest (all unit tests, excludes integration+legalbench)"
	@echo "  make test-frontend     - Frontend vitest"
	@echo "  make test-coverage     - Coverage reports for backend + frontend"
	@echo "  make test-smoke        - Repo-wide smoke + spec/backlog lint"
	@echo "  make test-specs        - Spec validator + backlog lint"
	@echo "  make test-integration  - Integration tests against real Neo4j/Postgres"
	@echo "  make test-legalbench   - LegalBench eval"
	@echo ""
	@echo "Quality:"
	@echo "  make lint              - ruff + black + frontend lint --fix (in containers)"
	@echo "  make format            - black + ruff fix + prettier (in containers)"
	@echo "  make typecheck         - mypy --strict + tsc --noEmit (in containers)"
	@echo ""
	@echo "Local AI stack (Spec 010):"
	@echo "  make local-ai-up       - Start postgres/redis/neo4j/ollama/phoenix"
	@echo "  make local-ai-down     - Stop the above"
	@echo "  make local-ai-pull     - Pull default Ollama models"
	@echo "  make local-ai-health   - Hit /api/agents/health/local-ai"
	@echo "  make validate-claude-code - Validate the dev-time Claude Code OAuth integration (LSAT)"
	@echo "  make lsat-author-demo  - Run the LSATContentAuthor agent live (via Claude Code when opted in)"
	@echo "  make legal-analyst-demo - Run the LegalAnalyst IRAC agent live (via Claude Code when opted in)"
	@echo ""
	@echo "Autonomy (Spec 018 — requires AUTONOMY_ENABLED=true):"
	@echo "  make autonomy-run KIND=corpus_growth SOURCE=courtlistener  - one cycle (also accepts AUTONOMY_KIND/SOURCE)"
	@echo "  make autonomy-run KIND=test_pillar BUDGET=10               - pillar A"
	@echo "  make autonomy-status                                       - show beat schedule"
	@echo "  make autonomy-stop                                         - stop consuming from autonomy queue (does NOT purge)"
	@echo ""
	@echo "Misc:"
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
	$(RUN_BACKEND_FULL) sh -c "python manage.py migrate && python manage.py ensure_checkpointer"

ingest:
	$(RUN_BACKEND_FULL) python scripts/ingest_sample.py --source courtlistener --limit 500

# ---------------------------------------------------------------------------
# Tests (Docker-only)
# ---------------------------------------------------------------------------

test: test-backend test-frontend

test-backend:
	$(RUN_BACKEND) pytest -m "not integration and not legalbench" -q --tb=short

test-frontend:
	$(RUN_FRONTEND) npm test -- --run

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

test-legalbench:
	$(RUN_BACKEND_FULL) python -m law_ai.eval.legalbench --subset core_reasoning,precedent_retrieval

# CI form: fails the build when a listed subset drops more than 1 pp against
# backend/var/legalbench/baseline.json (constitution §3). Exit codes are
# distinct — 1 = regression, 2 = the eval could not run (Ollama down / model
# not pulled), so a broken stack is never reported as a model regression.
test-legalbench-gate:
	$(RUN_BACKEND_FULL) python -m law_ai.eval.legalbench \
		--subset core_reasoning,precedent_retrieval --check-regression

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

typecheck:
	$(RUN_BACKEND) mypy law_ai --strict
	$(RUN_FRONTEND) npx tsc --noEmit

# ---------------------------------------------------------------------------
# Spec/backlog validators (lightweight — host stdlib only, no container)
# ---------------------------------------------------------------------------

lint-specs:
	python3 scripts/spec_validator.py
	python3 scripts/backlog_lint.py

evolve-audit:
	python3 scripts/evolve_audit.py
	$(MAKE) lint-specs

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

local-ai-health:
	@curl -fsS http://localhost:8000/api/agents/health/local-ai | python3 -m json.tool

validate-claude-code:
	$(RUN_BACKEND_FULL) python manage.py validate_claude_code

# Regenerate the static LSAT practice-site artifact (spec 025): export the
# bank in Docker, then copy it into the committed site directory that GitHub
# Pages deploys. tests/test_lsat_site.py fails CI when this is stale.
lsat-export:
	$(RUN_BACKEND) python manage.py lsat_export --out var/lsat_site
	cp backend/var/lsat_site/content.json lsat-static/content.json
	@echo "site data refreshed → lsat-static/content.json"

# Live LSATContentAuthor agent run. Routes through Claude Code when opted in
# (LSAT_LLM_PROVIDER=claude_code + token in backend/.env). Pass extra flags via
# ARGS, e.g. `make lsat-author-demo ARGS='--section RC --difficulty hard'`.
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
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

host-test:
	cd backend && pytest -q --cov=law_ai
	cd frontend && npm test -- --run

clean:
	$(DC) down -v
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf htmlcov/ .coverage backend/.venv frontend/.next
