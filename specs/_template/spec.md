# Spec: {Feature Name}

- **ID**: NNN-feature-slug
- **Status**: draft | clarified | planned | in-progress | shipped
- **Owner**: @github-handle
- **Created**: YYYY-MM-DD
- **Roadmap Epic**: link to issue / roadmap entry
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

What user / legal-research problem does this solve? Quote concrete user pain or roadmap OKR.

## 2. Goals

- G1: …
- G2: …

## 3. Non-Goals

- NG1: …

## 4. User Stories

- As a {role}, I want {capability}, so that {outcome}.

## 5. Functional Requirements

Use stable IDs — `tasks.md` and tests reference these.

- **FR-1**: …
- **FR-2**: …

## 6. Non-Functional Requirements

- **NFR-PERF-1**: e.g. p95 latency < 800 ms for `/api/analyze`.
- **NFR-SEC-1**: e.g. all external HTTP via `httpx` with retry + timeout.
- **NFR-AUDIT-1**: every agent call logged via `app.core.provenance`.
- **NFR-HITL-1**: declare `human_approval_required` for high-stakes paths.

## 7. Data Model Impact

Neo4j nodes/edges added or changed; Postgres tables; vector collections. Reference [docs/data-model.md](../../docs/data-model.md) sections affected. Every new node MUST carry `source`, `confidence`, `ingest_timestamp`.

## 8. API Surface

New / changed FastAPI routes with method, path, request, response models. Reference Pydantic models by name.

## 9. Agent / Crew Impact

Which agents in [docs/agent-roles.md](../../docs/agent-roles.md) are added, modified, or invoked. Note any new tools they need.

## 10. Acceptance Criteria

Each criterion must be objectively testable. Maps 1:N to tasks.

- **AC-1**: Given …, when …, then ….
- **AC-2**: …

## 11. LegalBench Impact

- Tasks affected: …
- Expected delta: ≥ 0 pp on listed tasks (or rationale for regression).

## 12. Risks & Open Questions

- **R-1**: …
- **OQ-1**: … (resolve via `/clarify` before moving to plan)

## 13. Out of Scope / Follow-ups

- …
