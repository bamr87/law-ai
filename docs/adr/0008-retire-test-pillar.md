# ADR 0008 — Retire the test pillar (autonomous test synthesis)

- **Status**: accepted
- **Date**: 2026-10-26
- **Spec**: none — a removal. The loop it retires shipped as Pillar A of [specs/018-autonomous-framework](../../specs/018-autonomous-framework/spec.md) (G2) and its review surfaces as BL-20260511-03 and BL-20260511-17.
- **Constitution clauses amended**: [§12 Autonomy Loop Invariants](../constitution.md#12-autonomy-loop-invariants) — invariant I5 retired
- **Supersedes / Superseded by**: amends [ADR 0003](0003-autonomy-orchestrator.md). Pillar A is removed; Pillar B (corpus growth), the digest and the LSAT content pillars stand as decided there.

## Context

Spec 018 gave the autonomy loop two pillars. Pillar B grows the *product*: `TopicFrontier` walks the knowledge graph and dispatches known sources through the ingestion quarantine. Pillar A grew the *repository*: `TestSynthesizer` read `coverage.xml` from `make test-coverage`, asked a model for pytest skeletons for the five thinnest-tested modules, and wrote them to `backend/tests/autonomy/proposed/` as `*.proposed.py`, skip-decorated, for a human to promote. Around it grew a product surface — `GET /api/agents/proposed-tests`, the `ProposedTestReview` queue on Agent Ops, the "lowest-coverage modules" panel on `/autonomy` — a nightly Celery beat entry, and a nightly workflow step that put the proposals on a draft PR.

On 2026-10-25 the development harness left this repository: the spec-driven loop, its gates, the weekly evolve audit and the GitFactory lines moved to the bamr87 fleet hub and are consumed by reference ([docs/spec-driven.md](../spec-driven.md)). The test pillar is the same kind of thing — code whose subject is this codebase rather than the law — but it was wired into the product: a Django view listing a directory of the repo's own test files, a React component on the operator dashboard, a beat entry in the worker, and a constitution invariant (§12 I5) about how it writes. A lawyer or a student never needs any of it, and an operator who does is operating the repository, not the platform.

The hub already owns the replacement. Its weekly `repo-evolution.yml` loop opens draft improvement PRs in each opted-in repo's own upstream, and its issue pipeline turns a filed gap into a mergeable PR; a coverage signal in the evolution brief is a small follow-up there. Neither needs a CrewAI crew, an Ollama call or an API endpoint inside Law AI.

## Decision

1. **Remove Pillar A end to end**: the `TestSynthesizer` crew and its prompt, the `test_pillar` cycle kind, the `autonomy-nightly-tests` beat entry, `law_ai.eval.coverage_audit`, `GET /api/agents/proposed-tests`, `GET /api/agents/autonomy/lowest-coverage`, `backend/tests/autonomy/proposed/`, the `ProposedTestReview` component, the lowest-coverage panel, and the nightly workflow's synthesis step and "proposed tests" draft-PR half. `run_autonomy` and `autonomy_cycle` default to `digest`, the one kind that is safe without a source.
2. **Retire constitution §12 I5** rather than delete it: the clause records that any future test synthesis returns under the same propose-only rule.
3. **Keep everything the product uses**: the `/autonomy` panels for LegalBench history, recent cycles and the quarantine queue; the review queue; Pillar B; the digest; the LSAT content pillars. The LegalBench harness stays — it measures the product's reasoning, not the repo's coverage.
4. **Where coverage goes now**: `make test-coverage` and CI's backend coverage floor (`--cov-fail-under=75`) remain the gate. Proposing tests for thin modules is the hub's evolution loop (opt in with `auto_evolve: true` in the fleet registry); feeding it the coverage report is tracked in `BACKLOG.md`.

## Consequences

- The Agent Ops page loses the proposed-test queue and `/autonomy` drops from four panels to three. `AutonomyRun` rows with `kind = "test_pillar"` remain readable history; no migration.
- `GET /api/agents/proposed-tests` and `GET /api/agents/autonomy/lowest-coverage` return 404. The API contract fixture (`frontend/__tests__/fixtures/api-schema.json`) is regenerated in the same change.
- The nightly draft PR carries only the discovery audit's `BACKLOG.md` entries.
- `AUTONOMY_ENABLED` and the other §12 invariants are untouched; nothing about ingestion, HITL or provenance changes.
- Autonomy Level stays 2 (§10).

## Alternatives Considered

1. **Keep the pillar, hide the UI.** Rejected: the view, the beat entry and the proposals directory would still be product code whose subject is the repository, and a hidden surface is the one nobody maintains.
2. **Port `TestSynthesizer` into the hub kit.** Rejected: it is a Django management-command runner over a CrewAI/Ollama call with a Law AI-specific coverage path. The hub's evolution loop is already a generic "improve the repo" agent with a brief; a coverage line in the brief is the right size.
3. **Keep only the lowest-coverage panel as a read-only operator view.** Rejected: it exists to point the pillar at its targets; without the pillar it is a `coverage.xml` viewer, which `make test-coverage`'s `htmlcov/` already is.
