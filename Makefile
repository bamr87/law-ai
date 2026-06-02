.PHONY: help setup dev down logs ps debug shell-backend shell-frontend manage \
	test test-backend test-frontend test-coverage test-smoke test-specs \
	test-integration test-legalbench \
	lint format typecheck migrate ingest \
	evolve-audit lint-specs \
	docs docs-serve docs-linkcheck docs-coverage \
	autonomy-run autonomy-status autonomy-stop \
	local-ai-up local-ai-down local-ai-pull local-ai-health \
	host-setup host-test clean

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
	@echo "LawGraph AI — Docker-first development"
	@echo ""
	@echo "Stack:"
	@echo "  make dev               - Start full stack (foreground, builds images)"
	@echo "  make down              - Stop and remove containers"
	@echo "  make logs              - Tail logs from all services"
	@echo "  make ps                - List running services"
	@echo "  make debug             - Start stack with debugpy/inspect attach ports"
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
	@echo "Docs (ADR 0004 — generated from source docstrings + DRF schema):"
	@echo "  make docs              - Build the Sphinx site (fails on warnings)"
	@echo "  make docs-serve        - Build, then serve at http://localhost:8001"
	@echo "  make docs-linkcheck    - Check internal + external links"
	@echo "  make docs-coverage     - Docstring-coverage gate (interrogate)"
	@echo ""
	@echo "Local AI stack (Spec 010):"
	@echo "  make local-ai-up       - Start postgres/redis/neo4j/ollama/phoenix"
	@echo "  make local-ai-down     - Stop the above"
	@echo "  make local-ai-pull     - Pull default Ollama models"
	@echo "  make local-ai-health   - Hit /api/agents/health/local-ai"
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
	$(RUN_BACKEND) pytest --cov=lawgraph --cov-report=xml --cov-report=html --cov-report=term
	$(RUN_FRONTEND) npm run test:coverage

test-smoke:
	$(RUN_BACKEND) pytest -m "not integration and not legalbench"

test-specs:
	python3 scripts/spec_validator.py
	python3 scripts/backlog_lint.py

test-integration:
	$(DC) up -d neo4j postgres redis --wait
	@trap '$(DC) down' EXIT INT TERM; \
	  $(DC) run --rm \
	    -e DATABASE_URL=postgresql://lawgraph:lawgraph-dev@postgres:5432/lawgraph \
	    -e NEO4J_URI=bolt://neo4j:7687 \
	    -e NEO4J_USER=neo4j \
	    -e NEO4J_PASSWORD=lawgraph-dev \
	    -e REDIS_URL=redis://redis:6379/0 \
	    backend pytest -m integration -v

test-legalbench:
	$(RUN_BACKEND_FULL) python -m lawgraph.eval.legalbench --subset core_reasoning,precedent_retrieval

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
	$(RUN_BACKEND) mypy lawgraph --strict
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
# Documentation (ADR 0004). The Python API reference is generated from source
# docstrings and the REST schema from the DRF views, so docs cannot drift.
# Runs on the host (like lint-specs) because the build spans docs/ (repo root)
# and the backend package. First: pip install -e "backend[docs]".
# ---------------------------------------------------------------------------
DOCS_OUT := docs/_build/html

docs:
	sphinx-build -b html -W --keep-going docs $(DOCS_OUT)

docs-serve: docs
	@echo "Serving docs at http://localhost:8001 (Ctrl-C to stop)"
	python3 -m http.server 8001 --directory $(DOCS_OUT)

docs-linkcheck:
	sphinx-build -b linkcheck docs docs/_build/linkcheck

docs-coverage:
	cd backend && interrogate lawgraph -c pyproject.toml

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

local-ai-pull:
	$(DC) exec ollama ollama pull mistral:7b-instruct-q4_K_M
	$(DC) exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
	$(DC) exec ollama ollama pull nomic-embed-text

local-ai-health:
	@curl -fsS http://localhost:8000/api/agents/health/local-ai | python3 -m json.tool

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
	$(RUN_WORKER) celery -A lawgraph inspect scheduled

autonomy-stop:
	# Stops the worker from consuming new tasks from the autonomy queue.
	# This does NOT purge tasks already queued — use 'celery purge' for that.
	$(RUN_WORKER) celery -A lawgraph control cancel_consumer autonomy

# ---------------------------------------------------------------------------
# Legacy host-based targets (avoid; emergency fallback only)
# ---------------------------------------------------------------------------

host-setup:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

host-test:
	cd backend && pytest -q --cov=lawgraph
	cd frontend && npm test -- --run

clean:
	$(DC) down -v
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf htmlcov/ .coverage backend/.venv frontend/.next
