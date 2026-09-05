# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for Law AI.

ADRs are the canonical place to record decisions that **deviate from or amend** [docs/constitution.md](../constitution.md) — particularly tech-stack changes, security model changes, or relaxations of mandatory gates. Every spec that proposes such a deviation MUST link to an ADR here (and the ADR must be merged in or before the same PR).

## Format

- File name: `NNNN-short-kebab-title.md` where `NNNN` is a four-digit sequence (`0001`, `0002`, …).
- Required sections: **Status**, **Context**, **Decision**, **Consequences**, **Alternatives Considered**, **Supersedes / Superseded by**.
- Status values: `proposed` / `accepted` / `superseded` / `deprecated`.

## Index

| ID    | Title                            | Status   | Constitution clauses touched |
| ----- | -------------------------------- | -------- | ---------------------------- |
| 0001  | [Adopt Django backend](0001-adopt-django-backend.md) | accepted | §2 (tech stack), §11 (mission-drift guard) |
| 0003  | [Autonomy orchestrator](0003-autonomy-orchestrator.md) | accepted | §10 (autonomy level), new §12 (autonomy loop invariants) |
| 0004  | [Jurisprudential stance](0004-jurisprudential-stance.md) | accepted | new §13 (jurisprudential honesty); reinforces §1, §4, §5 |
| 0005  | [Claude-default LLM provider chain](0005-claude-default-runtime.md) | accepted | §1 (product-runtime LLM policy) |
| 0006  | [First-party design system](0006-first-party-design-system.md) | proposed | §2 (drop shadcn/ui lock), §9 (docs/ui-ux.md) |
| 0007  | [xAI as a sanctioned runtime provider](0007-xai-runtime-provider.md) | accepted | §1 (product-runtime LLM policy — vendor closure), §2 (tech stack) |

`0002` was never assigned an ADR; the sequence intentionally jumps 0001 → 0003 rather than renumbering later entries.

Spec 035 (LangChain/LangGraph promoted to core, non-optional dependencies) was evaluated against this index's own rule and does **not** get an ADR: it makes no constitution amendment (§2 already sanctions LangGraph/CrewAI as tech stack; `langchain-core` is that same framework's substrate, not a new or competing framework choice), so [docs/constitution.md](../constitution.md) §1/§2 already is the durable record.
