# ADR 0003 — Autonomy Orchestrator (Two-Pillar Loop, Strict Level-2)

- **Status**: accepted
- **Date**: 2026-05-11
- **Spec**: [specs/018-autonomous-framework](../../specs/018-autonomous-framework/spec.md)
- **Constitution clauses amended**: [§10 Autonomy Level](../constitution.md#10-autonomy-level), new [§12 Autonomy Loop Invariants](../constitution.md#12-autonomy-loop-invariants)

## Context

The repo's only autonomous loop today is the weekly `/evolve` audit ([scripts/evolve_audit.py](../../scripts/evolve_audit.py) + [.github/workflows/evolve.yml](../../.github/workflows/evolve.yml)) that appends BACKLOG candidates from grep + coverage parsing. It does not measure reasoning quality (the [backend/lawgraph/eval/](../../backend/lawgraph/eval/) LegalBench harness referenced from [docs/legalbench.md](../legalbench.md) is empty), and it does not grow the corpus — every ingestion run is hand-driven via `make ingest`.

Legal content is effectively unbounded: statutes, regulations, opinions, and citations expand daily across jurisdictions. We need a sustained, auditable loop that (a) measures reasoning quality continuously and proposes test coverage for low-coverage modules, and (b) walks the existing knowledge graph for orphan citations / under-cited jurisdictions and dispatches *known* sources to fill the gaps.

## Decision

Add an **AutonomyOrchestrator** that coordinates two cooperating loops on top of the existing `/evolve` infrastructure:

1. **TestPilot** (Pillar A, kind=`test`): runs LegalBench, parses coverage, and a `TestSynthesizer` crew proposes pytest cases for the lowest-coverage modules. Proposals are written to `*.proposed.py` files decorated with `@pytest.mark.skip("autonomy-proposed")` and surfaced via a draft PR (label `autonomy`) — never executed by default, never merged automatically.
2. **CorpusGrowth** (Pillar B, kind=`content`): a `TopicFrontier` LangGraph workflow walks Neo4j (`scan_graph` → `prioritize` → `dispatch` → `summarize`) and dispatches queries against `SOURCE_REGISTRY` adapters. Every dispatched document still flows through `IngestionScout.run_and_commit`, so the existing confidence gate + `PendingReview` HITL queue are preserved. New `:Case` / `:Statute` nodes can be created only by `IngestionScout` — the orchestrator never writes to Neo4j directly.

Both pillars are invoked through one entry point — `python manage.py run_autonomy --kind {test,content,evolve}` and `lawgraph.core.autonomy.run_cycle()` — wrapped in a single `audit.AuditEvent` (`event_type='autonomy_cycle'`) per run. A daily `compose_digest` task writes `backend/var/autonomy/digest-<date>.md` enumerating PRs opened, BACKLOG items appended, docs quarantined, and the LegalBench delta. **The digest file is the canonical human-review surface.**

Three settings flags govern the loop:

- `AUTONOMY_ENABLED` (default `False`): global kill-switch. When false, `run_cycle` exits with a single `event_type='autonomy_disabled'` provenance event. No Celery dispatch, no HTTP, no Neo4j read.
- `AUTONOMY_ALLOWED_SOURCES` (default `[]`): allow-list of adapter names dispatch is permitted to call. Anything else emits `event_type='policy_violation'` and exits non-zero.
- `AUTONOMY_DIGEST_DIR` (default `backend/var/autonomy`): location of digest files.

Cadences:

- `nightly_tests` — daily 06:00 UTC via `.github/workflows/nightly-tests.yml` (CI keeps Ollama state hot enough for `--limit 20` runs).
- `weekly_evolve` — Mondays 13:00 UTC via the existing `.github/workflows/evolve.yml`.
- `content_sweep` — every 6h via Celery beat in the local `worker` service (CI runners cannot keep Ollama state hot for full sweeps; this runs on operator hardware via `make autonomy-up`).

## Reaffirmation: AO-SDLC Level 2 (no auto-merge)

This ADR explicitly retains the [§10 Autonomy Level](../constitution.md#10-autonomy-level) Level-2 stance. Every loop ends in either:

- a **draft PR** (code) that a human reviewer must mark ready + merge, or
- a **`PendingReview` row** (data) that a HITL reviewer must approve via Django admin.

No GitHub Actions workflow in this design is granted permissions sufficient to merge a PR; no Celery task may write to a `:Case`/`:Statute` node outside `IngestionScout.run_and_commit`. Promotion to Level 3 — even for narrow change classes — would require a separate ADR and a constitution amendment per [§10](../constitution.md#10-autonomy-level).

## Alternatives considered

1. **Self-hosted GitHub Actions runner for content sweeps.** Rejected for MVP — adds operator burden without unlocking new behavior; `make autonomy-up` on operator hardware is sufficient. May revisit if multiple operators need shared cadence.
2. **Append TestSynthesizer output directly into the real test file.** Rejected — defeats the propose-only stance; reviewer cannot easily distinguish autonomy-generated tests from human-authored ones; risk of breaking CI on a typo.
3. **Allow auto-merge for low-risk PR classes (test additions, doc backfills).** Rejected — would require constitution amendment per §10 and an explicit policy matrix; user explicitly chose strict Level 2 for legal-accuracy reasons.
4. **Free-form web scraping in TopicFrontier.** Rejected — constitution §5 makes "ingestion of a new public data source" a HITL gate; recursion expands within a closed `SOURCE_REGISTRY` whose names appear in `AUTONOMY_ALLOWED_SOURCES`. Adding a new source is its own `/specify` cycle.
5. **Promote `AutonomyRun` to its own Postgres table immediately.** Deferred — `audit.AuditEvent` carries enough JSON payload for v1 digest queries. Recorded as BL-20260511-04.

## Consequences

**Positive**

- Reasoning regressions become visible per-night (currently never).
- Coverage debt becomes a steady stream of reviewable proposals instead of an annual cleanup.
- Ingestion plan is data-driven: "you have N orphan citations, here are the M registered adapters that could resolve them" rather than ad-hoc.
- One audited entry point (`run_cycle` → `audit.AuditEvent`) means one digest, one review surface.

**Negative / risks**

- LegalBench latency on Mistral 7B may exceed 30 minutes/night on weak hardware. Mitigation: `--limit 20` default; full set monthly.
- TestSynthesizer noise. Mitigation: `*.proposed.py` + `@pytest.mark.skip` make every proposal opt-in.
- Operator confusion if `AUTONOMY_ENABLED=False` silently no-ops. Mitigation: `make autonomy-status` surfaces the flag; digest task records the disabled state explicitly.

## Compliance check

| Constitution clause | Compliance |
|---------------------|------------|
| §1 mission alignment, local-first | All LLM calls go through the existing local Ollama client. No closed-source fallback. |
| §2 tech stack | Uses Django + Celery + LangGraph + Pydantic + httpx + tenacity already in §2. No new top-level frameworks. |
| §4 provenance & audit | Every cycle, every adapter dispatch, every LLM call logged via `lawgraph.core.provenance`. |
| §5 HITL | New data sources still gated by `/specify`; low-confidence ingest still goes to `PendingReview`. |
| §10 autonomy level | Level 2 explicitly retained; this ADR is the recorded reaffirmation. |
| §11 continuous evolution | Loop appends BACKLOG items; never deletes; spec-driven additions of new adapters preserved. |
| New §12 autonomy invariants | This ADR is the source of those invariants. |
