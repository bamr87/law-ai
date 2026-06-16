# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for LawGraph AI.

ADRs are the canonical place to record decisions that **deviate from or amend** [docs/constitution.md](../constitution.md) — particularly tech-stack changes, security model changes, or relaxations of mandatory gates. Every spec that proposes such a deviation MUST link to an ADR here (and the ADR must be merged in or before the same PR).

## Format

- File name: `NNNN-short-kebab-title.md` where `NNNN` is a four-digit sequence (`0001`, `0002`, …).
- Required sections: **Status**, **Context**, **Decision**, **Consequences**, **Alternatives Considered**, **Supersedes / Superseded by**.
- Status values: `proposed` / `accepted` / `superseded` / `deprecated`.

## Index

| ID    | Title                            | Status   | Constitution clauses touched |
| ----- | -------------------------------- | -------- | ---------------------------- |
| 0001  | [Adopt Django backend](0001-adopt-django-backend.md) | accepted | §2 (tech stack), §11 (mission-drift guard) |
| 0003  | [Autonomy Orchestrator (two-pillar loop)](0003-autonomy-orchestrator.md) | accepted | §10 (autonomy level), §12 (new — loop invariants) |
| 0004  | [Claude Code autonomy surface + narrow auto-merge](0004-claude-autonomy-surface.md) | proposed | §10, §12 (I1 amended), §13 (new) |
