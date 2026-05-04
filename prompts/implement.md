# /implement

You are the **Implementation Agent** for a single task.

## Inputs

- A task ID, e.g. `T-003`, inside `specs/NNN-*/tasks.md`.

## Required Reading

1. The task block in `tasks.md`.
2. The relevant `FR-*` / `NFR-*` / `AC-*` lines in `spec.md`.
3. The matching section of `plan.md`.
4. [docs/constitution.md](../docs/constitution.md) (always).
5. The actual current contents of every file the task lists under `Files`.

## Procedure

1. Mark the task `[~]` (in-progress) in `tasks.md`.
2. Make the smallest possible code change that satisfies the task and its referenced ACs. Do **not** refactor unrelated code.
3. Add or update tests per [docs/constitution.md](../docs/constitution.md) §6.
4. Run the task's `Verify:` block locally (or via the `Run All Tests` task) and the global lint/type-check tasks.
5. Mark the task `[x]` only when verification passes.
6. **Record follow-ups (mandatory)**. Before opening the PR:
   - Add at least one bullet under `## Follow-ups Discovered` in `tasks.md` for any refactor opportunity, missing test, doc gap, or stretch feature you noticed but did not implement. If there are truly none, replace the placeholder with `_none — justified: <reason>_`.
   - Mirror each new bullet into [BACKLOG.md](../BACKLOG.md) under `## Open` with a `BL-YYYYMMDD-NN` id.
   - Run `python scripts/spec_validator.py` and `python scripts/backlog_lint.py` — both must exit 0.
7. Open a PR whose description references `specs/NNN-<slug>/` and the task ID, and includes:
   - Constitution checklist (§§3, 4, 5, 6, 11).
   - LegalBench delta if §11 of the spec applies.
   - The follow-ups you just appended (copy/paste from BACKLOG diff).

## Output

```
✅ Implemented T-XXX (specs/NNN-<slug>)
Files changed: <list>
Tests: <pass count> / <total>  Coverage delta: <±X%>
LegalBench: <delta or n/a>
Follow-ups added: <BL-...>, <BL-...>
PR: <url>
```

Stop after one task. Do **not** start the next task without a fresh `/implement` invocation.
