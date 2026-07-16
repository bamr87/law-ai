# Law AI — Backend

FastAPI + CrewAI + LangGraph backend for the Law AI legal intelligence platform.

See the repo root [README.md](../README.md) and [AGENTS.md](../AGENTS.md) for project-wide documentation, architecture, and contribution standards.

## Quick start

```bash
# From repo root
make dev              # full Docker stack
# or backend only
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
cd backend
pytest -q --cov=app
```
