# Repo-wide test entry point

This top-level `tests/` package is the single command surface for validating the Law AI monorepo. It complements — but does **not** replace — the per-stack suites under [backend/tests/](../backend/tests) and [frontend/__tests__/](../frontend/__tests__).

## Layers (pytest markers)

| Marker | What it covers | Default? | Cost |
|--------|----------------|----------|------|
| `smoke` | Repo structure, required files/dirs, config sanity, docs presence, dead links | ✅ yes | <1s |
| `specs` | Runs the fleet's `spec_validator.py --strict` and `backlog_lint.py` as tests ([test_spec_gate.py](test_spec_gate.py)); the tools come from the hub's spec-driven kit via `tools/fleet-kit.sh` and the tier skips when the kit cannot be resolved | ✅ yes | ~1s |
| `backend` | Shells out to backend `pytest` (uses `backend/pyproject.toml`) | ❌ opt-in | slow |
| `frontend` | Shells out to `npm test -- --run` (vitest) | ❌ opt-in | slow |
| `slow` | Anything expected to take >5s | ❌ opt-in | — |

## Common invocations

```bash
# Default fast tier — structure, configs, docs, the spec/backlog gates.
pytest

# Same, plus the full backend suite.
pytest -m "smoke or specs or backend"

# Full repo: everything, including frontend (needs node_modules).
pytest -m "smoke or specs or backend or frontend"
```

## Running from the Makefile

The `make` targets below wrap `docker compose run --rm <service>` (or, for `lint-specs`, run the hub's stdlib gates on the host through `tools/fleet-kit.sh`) — they call into the per-stack suites, **not** through this root orchestrator's markers:

```bash
make test-backend    # backend pytest suite only (excludes integration + legalbench)
make test-frontend   # frontend vitest only, via npm test -- --run
make test            # test-backend + test-frontend
make lint-specs      # the fleet's spec_validator.py --strict + backlog_lint.py, then scripts/ux_audit.py (host)
```

`make test-smoke` currently also shells into the backend container and runs the same suite as `make test-backend` — it does not invoke this root `tests/` package's `smoke`/`specs` tier or the gate scripts, despite the name. To run this package's own `smoke`/`specs` markers (or the full `smoke or specs or backend or frontend` combination) directly, use the `pytest` invocations under "Common invocations" above from the repo root — they're deliberately dependency-light (stdlib + pytest only) and are what CI's `repo-structural` job runs on the bare GitHub runner, outside Docker.

## Where the spec-driven machinery went

Until 2026-10-25 this package carried `test_specs_and_backlog.py`, `test_backlog_picker.py` and `test_evolve_audit.py`, which tested the repo's own copies of the AO-SDLC gates under `scripts/`. Those scripts, the prompt chain, the gate hook and the weekly evolve workflow now live in the fleet hub ([bamr87/bamr87 templates/spec-driven](https://github.com/bamr87/bamr87/tree/main/templates/spec-driven)) with their own test (`test_spec_driven_kit.py`), and this repo consumes them by reference ([docs/spec-driven.md](../docs/spec-driven.md)). `test_docs.py::test_spec_driven_loop_is_consumed_by_reference` and `test_configs.py` guard that nothing creeps back.

## Design notes

- The root `pytest.ini` deliberately excludes `backend/`, `frontend/`, `node_modules/`, `.venv/`, and `specs/_template/` from collection so this suite never accidentally double-runs the per-stack tests.
- Backend and frontend orchestrators run as **subprocesses** so each stack keeps ownership of its own config, coverage thresholds, and fixtures (per [AGENTS.md](../AGENTS.md) Testing Standards).
- All tests must remain dependency-light: standard library + `pytest` (+ PyYAML for the workflow-parsing config gates, which skip without it). Anything heavier belongs in the per-stack suites.
