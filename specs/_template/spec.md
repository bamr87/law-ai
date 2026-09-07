# Spec: {Feature Name}

- **ID**: NNN-feature-slug
- **Status**: draft | clarified | planned | in-progress | shipped
- **Owner**: @github-handle
- **Created**: YYYY-MM-DD
- **Roadmap Epic**: link to issue / roadmap entry
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

What user / legal-research problem does this solve? Quote concrete user pain or roadmap OKR.

## 2. Origin & Background

- Backlog items claimed: **BL-YYYYMMDD-NN** (move each matching bullet from `## Open` to `## Claimed` in [BACKLOG.md](../../BACKLOG.md), annotated `claimed-by:specs/NNN-<slug>`), or "none — direct request".
- Prior art: the specs / ADRs this builds on or supersedes, and what changed since.
- **Review question (constitution §13)**: does this feature rank, score, or summarise legal authority? If **yes**, answer here — *who is the stronger here, and what does this feature do for them?* — naming the party the ranking advantages and how the design keeps the signal labelled as what it measures rather than as correctness. If **no**, say so in one line; [docs/constitution.md](../../docs/constitution.md) §13 requires the answer at spec review, not at PR review.

## 3. Goals

- G1: …
- G2: …

## 4. Non-Goals

- NG1: …

## 5. User Stories

- As a {role}, I want {capability}, so that {outcome}.

## 6. Functional Requirements

Use stable IDs — `tasks.md` and tests reference these.

- **FR-1**: …
- **FR-2**: …

## 7. Non-Functional Requirements

- **NFR-PERF-1**: e.g. p95 latency < 800 ms for `/api/analyze`.
- **NFR-SEC-1**: e.g. all external HTTP via `httpx` with retry + timeout.
- **NFR-AUDIT-1**: every agent call logged via `app.core.provenance`.
- **NFR-HITL-1**: declare `human_approval_required` for high-stakes paths.

## 8. Data Model Impact

Neo4j nodes/edges added or changed; Postgres tables; vector collections. Reference [docs/data-model.md](../../docs/data-model.md) sections affected. Every new node MUST carry `source`, `confidence`, `ingest_timestamp`.

## 9. API Surface

New / changed FastAPI routes with method, path, request, response models. Reference Pydantic models by name.

## 10. Agent / Crew Impact

Which agents in [docs/agent-roles.md](../../docs/agent-roles.md) are added, modified, or invoked. Note any new tools they need.

## 11. Acceptance Criteria

Each criterion must be objectively testable. Maps 1:N to tasks.

- **AC-1**: Given …, when …, then ….
- **AC-2**: …

## 12. LegalBench Impact

- Tasks affected: …
- Expected delta: ≥ 0 pp on listed tasks (or rationale for regression).

## 13. Risks & Open Questions

- **R-1**: …
- **OQ-1**: … (resolve via `/clarify` before moving to plan)

## 14. Out of Scope / Follow-ups

- …
