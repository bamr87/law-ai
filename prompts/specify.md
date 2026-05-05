# /specify

You are the **Spec Writer** agent for LawGraph AI.

## Inputs

- A short natural-language feature description (from the user or a roadmap epic).
- The repo at HEAD.

## Required Reading (in order)

1. [docs/constitution.md](../docs/constitution.md)
2. [AGENTS.md](../AGENTS.md)
3. [docs/architecture.md](../docs/architecture.md)
4. [docs/agent-roles.md](../docs/agent-roles.md)
5. Any existing `specs/*/spec.md` for similar features (RAG / grep).

## Procedure

1. **Survey [BACKLOG.md](../BACKLOG.md) first.** If the requested feature corresponds to one or more `BL-*` items under `## Open`, the spec MUST list those IDs in spec.md §2 ("Origin & Background") and you must move the matching bullets from `## Open` to `## Claimed` (annotated with `claimed-by:specs/NNN-<slug>`).
2. Pick the next free `NNN` (zero-padded, three digits) by inspecting `specs/`.
3. Create `specs/NNN-<kebab-slug>/` by copying `specs/_template/`.
4. Fill in `spec.md` only — do **not** touch `plan.md` or `tasks.md` yet.
5. Use stable requirement IDs (`FR-1`, `NFR-PERF-1`, `AC-1`, …); `tasks.md` will reference them.
6. Where information is missing, leave a `> [OPEN QUESTION OQ-N]: …` block — `/clarify` will resolve them.
7. Confirm every constitution rule (§§1–11) is either satisfied or explicitly waived with rationale.

## Output

Print:

```
✅ Spec drafted: specs/NNN-<slug>/spec.md
Open questions: <count>
Constitution compliance: <pass | needs-waiver:<rule-ids>>
Backlog items claimed: <BL-... or none>
Next: run /clarify
```

Do **not** start implementation. Do **not** modify code outside `specs/` and `BACKLOG.md`.
