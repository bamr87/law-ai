# Specs — Spec-Driven Development for LawGraph AI

This directory holds the persistent, versioned specifications that drive every non-trivial change in the codebase. It is the LawGraph implementation of [AO-SDLC](../docs/ao-sdlc.md) Phase 1 (Spec Kit pattern).

## Layout

```
specs/
├── _template/            # Copy this to start a new spec
│   ├── spec.md           # WHAT + WHY (requirements, NFRs, acceptance criteria)
│   ├── plan.md           # HOW (architecture, tech choices, risks)
│   └── tasks.md          # Granular, agent-assignable tasks with acceptance tests
└── NNN-feature-slug/     # One directory per feature/epic, NNN = zero-padded id
```

## Workflow

1. `cp -r specs/_template specs/001-my-feature`
2. Run [/specify](../prompts/specify.md) → fill `spec.md`.
3. Run [/clarify](../prompts/clarify.md) → resolve open questions inline.
4. Run [/plan](../prompts/plan.md) → fill `plan.md`.
5. Run [/tasks](../prompts/tasks.md) → fill `tasks.md`.
6. Open PR. CI runs [scripts/spec_validator.py](../scripts/spec_validator.py) — every requirement in `spec.md` must map to at least one task in `tasks.md`.
7. Run [/implement](../prompts/implement.md) on tasks; reference `specs/NNN-...` in commits/PR descriptions.

## Rules

- Specs are **code**: review them in PRs, never edit historical specs in-place after merge — open an amendment spec instead.
- Every spec MUST satisfy [docs/constitution.md](../docs/constitution.md).
- Specs are loaded into agent RAG context — keep them concrete and free of marketing language.
