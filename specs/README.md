# Specs — Spec-Driven Development for Law AI

This directory holds the persistent, versioned specifications that drive every non-trivial change in the codebase: the Law AI content of the fleet's spec-driven loop ([docs/spec-driven.md](../docs/spec-driven.md)). The machinery that validates and drives them — the `/spec-driven:*` chain, the spec validator, the backlog lint — is the fleet hub's, consumed by reference; nothing here depends on a script in this repo.

## Layout

```
specs/
├── _template/              # Copy this to start a new spec (repo-owned; seeded once from the hub kit)
│   ├── spec.md             # WHAT + WHY (requirements, NFRs, acceptance criteria, the §13 review question)
│   ├── plan.md             # HOW (architecture, tech choices, risks)
│   └── tasks.md            # Granular, agent-assignable tasks with acceptance tests + Follow-ups Discovered
├── _review_questions.json  # The questions a spec must answer (constitution §13), read by the validator
└── NNN-feature-slug/       # One directory per feature/epic, NNN = zero-padded id
```

## Workflow

1. `/spec-driven:specify <BL-id or intent>` → claims the backlog item and fills `spec.md` (copies `_template/`).
2. `/spec-driven:clarify <slug>` → resolves open questions inline.
3. `/spec-driven:plan <slug>` → fills `plan.md`.
4. `/spec-driven:tasks <slug>` → fills `tasks.md`.
5. Open PR. CI's `Spec Drift Gate` runs the fleet's `spec_validator.py --strict` — every requirement in `spec.md` must map to at least one task in `tasks.md`, every open question must be resolved, and every review question answered. `make lint-specs` runs the same gate locally.
6. `/spec-driven:implement T-NNN` on tasks; reference `specs/NNN-...` in commits/PR descriptions; mirror follow-ups into [BACKLOG.md](../BACKLOG.md).

## Rules

- Specs are **code**: review them in PRs, never edit historical specs in-place after merge — open an amendment spec instead.
- Every spec MUST satisfy [docs/constitution.md](../docs/constitution.md).
- Specs are loaded into agent RAG context — keep them concrete and free of marketing language.
