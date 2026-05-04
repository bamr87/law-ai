# Repo-wide test entry point

This top-level `tests/` package is the single command surface for
validating the LexGraph AI monorepo. It complements — but does **not**
replace — the per-stack suites under [backend/tests/](../backend/tests)
and [frontend/__tests__/](../frontend/__tests__).

## Layers (pytest markers)

| Marker | What it covers | Default? | Cost |
|--------|----------------|----------|------|
| `smoke` | Repo structure, required files/dirs, config sanity, docs presence | ✅ yes | <1s |
| `specs` | Runs `scripts/spec_validator.py` and `scripts/backlog_lint.py` as tests | ✅ yes | ~1s |
| `backend` | Shells out to backend `pytest` (uses `backend/pyproject.toml`) | ❌ opt-in | slow |
| `frontend` | Shells out to `npm test -- --run` (vitest) | ❌ opt-in | slow |
| `slow` | Anything expected to take >5s | ❌ opt-in | — |

## Common invocations

```bash
# Default fast tier — structure, configs, docs, spec/backlog linters.
pytest

# Same, plus the full backend suite.
pytest -m "smoke or specs or backend"

# Full repo: everything, including frontend (needs node_modules).
pytest -m "smoke or specs or backend or frontend"
```

Convenience targets:

```bash
make test-smoke      # smoke + specs only (CI-fast)
make test-backend    # smoke + specs + backend
make test-frontend   # smoke + specs + frontend
make test-all        # everything via this entry point
```

## Design notes

- The root `pytest.ini` deliberately excludes `backend/`, `frontend/`,
  `node_modules/`, `.venv/`, and `specs/_template/` from collection so
  this suite never accidentally double-runs the per-stack tests.
- Backend and frontend orchestrators run as **subprocesses** so each
  stack keeps ownership of its own config, coverage thresholds, and
  fixtures (per [AGENTS.md](../AGENTS.md) Testing Standards).
- All tests must remain dependency-light: standard library + `pytest`
  only. Anything heavier belongs in the per-stack suites.
