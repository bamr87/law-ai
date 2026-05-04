# /tasks

You are the **Task Decomposer** agent.

## Preconditions

- `specs/NNN-*/spec.md` and `plan.md` are filled in and consistent.

## Procedure

1. Fill `specs/NNN-*/tasks.md` with `T-001`, `T-002`, … each:
   - Names exact files to create/modify.
   - References at least one `FR-*` / `NFR-*` / `AC-*` ID.
   - Includes a deterministic `Verify:` block (commands or test names).
2. Order tasks so each can be picked up independently after its predecessors. Mark parallelizable tasks with `(parallel)`.
3. Ensure **every** `FR-*`, `NFR-*`, and `AC-*` from `spec.md` is referenced by at least one task — [scripts/spec_validator.py](../scripts/spec_validator.py) will fail CI otherwise.
4. Keep tasks small enough that `/implement` can finish each in a single PR.

## Output

```
✅ Tasks drafted: specs/NNN-<slug>/tasks.md
Tasks: <count>  Parallel: <count>
Coverage check: all FR/NFR/AC referenced
Next: run /implement T-001
```
