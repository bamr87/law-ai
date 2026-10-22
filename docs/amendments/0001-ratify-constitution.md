<!-- kit: governance v0.1.0 -->
# 0001 — Ratify the constitution

- **Status:** ratified
- **Date:** 2026-10-21
- **Proposed by:** bamr87 fleet governance kit (bamr87/bamr87 templates/governance/)
- **Ratified by:** the merged PR that adds this record (docs/feature-catalog)
- **Affects:** whole constitution; feature catalog and PRD link (UPS-WORK-15, UPS-WORK-16)
- **Supersedes:** none
- **Related:** [docs/constitution.md](../constitution.md), [features/features.yml](../../features/features.yml)

## Context

law-ai already has a constitution (docs/constitution.md, the fleet's reference one), amended inline with dated notes tied to ADRs (§1: spec 034, ADR 0007). What it lacked was a numbered, append-only record of those amendments that agents can read and the fleet lint can check.

## Amendment

Keep [docs/constitution.md](../constitution.md) unchanged in substance and add § 14 Amendments, making this log (alongside the existing ADR requirement) the change path. Prior inline amendments are recognized as ratified history.

## Consequences

Agents read the constitution first (AGENTS.md links it). Every feature carries a stable id in the catalog, linked to the PRD requirements it serves; the PRD carries the generated feature block.
