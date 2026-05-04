# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for LexGraph AI.

ADRs are the canonical place to record decisions that **deviate from or amend** [docs/constitution.md](../constitution.md) — particularly tech-stack changes, security model changes, or relaxations of mandatory gates. Every spec that proposes such a deviation MUST link to an ADR here (and the ADR must be merged in or before the same PR).

## Format

- File name: `NNNN-short-kebab-title.md` where `NNNN` is a four-digit sequence (`0001`, `0002`, …).
- Required sections: **Status**, **Context**, **Decision**, **Consequences**, **Alternatives Considered**, **Supersedes / Superseded by**.
- Status values: `proposed` / `accepted` / `superseded` / `deprecated`.

## Index

| ID    | Title                            | Status   | Constitution clauses touched |
| ----- | -------------------------------- | -------- | ---------------------------- |
| 0001  | [Adopt Django backend](0001-adopt-django-backend.md) | accepted | §2 (tech stack), §11 (mission-drift guard) |
