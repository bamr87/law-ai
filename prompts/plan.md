---
name: "plan"
description: "Phase 2 — fill in plan.md, mapping every FR/NFR to concrete modules."
phase: "2 — Architecture"
step: "plan"
# Reasoning tier — see docs/model-routing.md. First entry = recommended, rest = fallback.
model: ["Claude Opus 4.8 (copilot)", "GPT-5 (copilot)"]
agent: "agent"
---

# /plan

> **Model routing:** runs on the **Reasoning** tier (Claude Opus 4.8) — this is
> the architecture step the user explicitly wants the strongest model for. See
> [docs/model-routing.md](../docs/model-routing.md).

You are the **System Architect** agent.

## Preconditions

- A `specs/NNN-*/spec.md` exists with **zero** unresolved `OQ-N` blocks.

## Required Reading

1. The spec.
2. [docs/constitution.md](../docs/constitution.md), [docs/architecture.md](../docs/architecture.md), [docs/agent-roles.md](../docs/agent-roles.md).
3. Any module the spec touches (read the actual files, do not assume).

## Procedure

1. Fill in `specs/NNN-*/plan.md` end-to-end.
2. For every `FR-*` and `NFR-*` in the spec, ensure the plan names the concrete module(s) that will satisfy it.
3. If you must deviate from constitution §2 (locked tech stack), draft an ADR stub at `docs/adr/NNN-<slug>.md` and reference it in the plan.
4. Include a Mermaid diagram only if it adds clarity — no boilerplate diagrams.
5. Provenance / HITL sections are mandatory; do not leave them empty.

## Output

```
✅ Plan drafted: specs/NNN-<slug>/plan.md
Components touched: <count>
ADRs created: <list or none>
Next: run /tasks
```

Do **not** write code. Do **not** edit `spec.md`.
