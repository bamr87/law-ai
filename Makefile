.PHONY: help setup dev test test-smoke test-backend test-frontend test-all test-integration \
	lint format clean ingest evolve-audit lint-specs migrate \
	local-ai-up local-ai-down local-ai-pull local-ai-health

help:
	@echo "LawGraph AI - Development Commands"
	@echo ""
	@echo "  make setup          - Install all dependencies (backend + frontend)"
	@echo "  make dev            - Start full stack with Docker Compose"
	@echo "  make test           - Run all tests (backend + frontend, legacy)"
	@echo "  make test-smoke     - Repo-wide smoke + spec/backlog lint (fast)"
	@echo "  make test-backend   - Smoke + specs + backend pytest suite"
	@echo "  make test-frontend  - Smoke + specs + frontend vitest suite"
	@echo "  make test-all       - Everything via the root tests/ entry point"
	@echo "  make test-integration - Docker-backed integration tests (Neo4j + Postgres)"
	@echo "  make lint           - Run formatters and linters"
	@echo "  make clean          - Remove build artifacts and caches"

setup:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

dev:
	docker compose up --build

test:
	cd backend && pytest -q --cov=lawgraph
	cd frontend && npm test -- --run

migrate:
	cd backend && python manage.py migrate && python manage.py ensure_checkpointer

test-smoke:
	pytest -m "smoke or specs"

test-backend:
	pytest -m "smoke or specs or backend"

test-frontend:
	pytest -m "smoke or specs or frontend"

test-all:
	pytest -m "smoke or specs or backend or frontend"

test-integration:
	docker compose up -d neo4j postgres redis --wait
	cd backend && pytest -m integration -v
	docker compose down

lint:
	cd backend && ruff check --fix && black .
	cd frontend && npm run lint -- --fix

format:
	cd backend && black . && ruff check --fix
	cd frontend && prettier --write .

ingest:
	cd backend && python scripts/ingest_sample.py --source courtlistener --limit 500

lint-specs:
	python3 scripts/spec_validator.py
	python3 scripts/backlog_lint.py

evolve-audit:
	python3 scripts/evolve_audit.py
	$(MAKE) lint-specs

# === Spec 010: Local AI stack (Ollama + Postgres + Phoenix + backend) ===

local-ai-up:
	docker compose up -d postgres redis neo4j ollama phoenix
	@echo "Local AI stack starting. Models will pull in background."
	@echo "Phoenix UI:    http://localhost:6006"
	@echo "Ollama tags:   curl localhost:11434/api/tags"

local-ai-down:
	docker compose stop ollama phoenix postgres redis neo4j

local-ai-pull:
	docker compose exec ollama ollama pull mistral:7b-instruct-q4_K_M
	docker compose exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
	docker compose exec ollama ollama pull nomic-embed-text

local-ai-health:
	@curl -fsS http://localhost:8000/api/agents/health/local-ai | python3 -m json.tool

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "node_modules" -prune -o -name ".next" -prune -o -name "coverage" -prune
	rm -rf htmlcov/ .coverage backend/.venv frontend/.next