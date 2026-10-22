# Repo-wide test entry point

> The root `tests/` suite: dependency-light structural, docs, config and spec checks that run on the host and in CI's repo-structural job, plus opt-in backend and frontend orchestrators.

This top-level `tests/` package is the single command surface for validating the Law AI monorepo. It complements — but does **not** replace — the per-stack suites under [backend/tests/](../backend/tests) and [frontend/__tests__/](../frontend/__tests__).

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

## Running from the Makefile

The `make` targets below wrap `docker compose run --rm <service>` (or, for `lint-specs`, run the two linter scripts directly on the host) — they call into the per-stack suites, **not** through this root orchestrator's markers:

```bash
make test-backend    # backend pytest suite only (excludes integration + legalbench)
make test-frontend   # frontend vitest only, via npm test -- --run
make test            # test-backend + test-frontend
make lint-specs      # spec_validator.py + backlog_lint.py + ux_audit.py + test_evolve_audit.py (host)
```

`make test-smoke` currently also shells into the backend container and runs the same suite as `make test-backend` — it does not invoke this root `tests/` package's `smoke`/`specs` tier or the lint scripts, despite the name. To run this package's own `smoke`/`specs` markers (or the full `smoke or specs or backend or frontend` combination) directly, use the `pytest` invocations under "Common invocations" above from the repo root — they're deliberately dependency-light (stdlib + pytest only) and are what CI's `repo-structural` job runs on the bare GitHub runner, outside Docker.

## Host-side script coverage

`test_evolve_audit.py` exercises `scripts/evolve_audit.py`'s two substantive scanners (`_scan_coverage`, `_scan_legalbench`) from the host (BL-20260511-14, BL-20260511-15). The backend suite covers the same scanners, but the tests there load the script from the filesystem and used to skip inside Docker, which is where the backend suite runs — so in practice they had never executed in CI. That skip is fixed (`backend/tests/eval/test_coverage_audit.py` now also looks at `/repo/scripts/`), and this module is the host tier's independent copy.

**Wired into `make lint-specs`** (BL-20260511-14). That target used to be three stdlib scripts and nothing else, and running the audit's own coverage only in CI meant the person editing `scripts/evolve_audit.py` got no signal until a PR run. The target now runs `python3 -m pytest tests/test_evolve_audit.py -q` after the three scripts. pytest is the one non-stdlib thing it needs, and the recipe checks for it first and says so in one line rather than dying in a traceback — install it with `python3 -m pip install --user pytest`, or run the same checks in Docker. CI's `repo-structural` job still runs this package bare, so the gate holds on both surfaces.

## Design notes

- The root `pytest.ini` deliberately excludes `backend/`, `frontend/`,
`node_modules/`, `.venv/`, and `specs/_template/` from collection so this suite never accidentally double-runs the per-stack tests.
- Backend and frontend orchestrators run as **subprocesses** so each
stack keeps ownership of its own config, coverage thresholds, and fixtures (per [AGENTS.md](../AGENTS.md) Testing Standards).
- All tests must remain dependency-light: standard library + `pytest`
  only. Anything heavier belongs in the per-stack suites.
