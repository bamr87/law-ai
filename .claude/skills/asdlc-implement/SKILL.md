---
name: asdlc-implement
description: AO-SDLC step 5 — implement tasks.md task-by-task with green gates, in Docker. Use when asked to implement a spec, build the tasks, code a planned change, or continue the AO-SDLC chain after tasks.
---

Runs the AO-SDLC **implement** step. Full instructions: [prompts/implement.md](prompts/implement.md) (or [prompts/implement-feature.md](prompts/implement-feature.md) for a feature with no spec) — read it and execute it. Paths are relative to the repo root.

## Preconditions
- `specs/NNN-*/tasks.md` exists with `T-NNN` tasks. Implement them in order.

## Run (everything in Docker via `make` — never host pytest/ruff/mypy)
1. Read and follow [prompts/implement.md](prompts/implement.md); implement each task with its tests.
2. Close the loop (constitution §11): ensure `tasks.md` `## Follow-ups Discovered` is populated, mirror each into `BACKLOG.md ## Open` (`python3 scripts/next_backlog_id.py`), move the claimed `BL-*` to `## Done` with the PR link, and copy the new BACKLOG bullets into the PR description.
3. **Verify gates — all must exit 0:**
   ```bash
   python3 scripts/spec_validator.py
   python3 scripts/backlog_lint.py
   make test        # backend pytest + frontend vitest, in containers
   make lint        # ruff + black + frontend lint
   make typecheck   # mypy --strict + tsc
   ```
4. Open a PR referencing `specs/NNN-*`. For autonomous runs, open it as a **draft** (constitution §12 I1 — no auto-merge).

## Next
→ `asdlc-evolve` to pick the next backlog item.
