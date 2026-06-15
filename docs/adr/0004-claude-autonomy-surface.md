# ADR 0004 — Claude Code Autonomous Dev Surface + Narrow Auto-Merge Class

- **Status**: proposed — _ratified on merge by a human maintainer (constitution §amendment rule)_
- **Date**: 2026-06-15
- **Surfaced in**: branch `claude/cranky-burnell-fd2782` (AO-SDLC framework review, WS5)
- **Constitution clauses amended**: [§10 Autonomy Level](../constitution.md#10-autonomy-level), [§12 Autonomy Loop Invariants](../constitution.md#12-autonomy-loop-invariants), new [§13 Claude Code Autonomy Surface](../constitution.md#13-claude-code-autonomy-surface)

## Context

The autonomous loop today routes only to **GitHub Copilot**: `.github/workflows/evolve.yml` runs the discovery half of `/evolve` (`scripts/evolve_audit.py` → appends BACKLOG → files an issue assigned to `@copilot`). Claude Code is a sanctioned dev surface (§1, AGENTS.md) and is now wired as a dev-time LLM provider, but nothing drives the *implement-a-backlog-item* loop through it. ADR 0003 established the two Celery autonomy pillars (TestPilot, CorpusGrowth) under a strict Level-2 posture with six invariants (§12 I1–I6); the `evolve` dev loop was named there but never built.

We want AI agents to **continuously** advance the repo — fix issues, implement backlog items, create specs, test, and track all changes — with the Agent Ops dashboard surfacing the activity. WS1/WS3/WS4 (same review) delivered the Claude-native lifecycle skills, the dashboard mission-control endpoints, and the end-to-end change ledger. This ADR governs the remaining piece: an **unattended Claude Code evolve loop** and the safety posture it runs under.

The maintainer's stated preference (this review) is to **carve a single, narrow auto-merge class** rather than keep strict draft-PR-only forever.

## Decision

### 1. Claude Code is a first-class autonomous dev surface (new §13)

`/asdlc-evolve` (the Claude Code skill, runbook [prompts/evolve.md](../../prompts/evolve.md)) may run **unattended** on a schedule via [.github/workflows/evolve-claude.yml](../../.github/workflows/evolve-claude.yml), picking the top `## Open` BACKLOG item and driving the full chain to a PR. It inherits ADR-0003's invariants verbatim:

- **I4 one audited entry / I6 provenance** — every cycle records a `SessionRun` (WS4) and emits provenance; the daily digest, `GET /api/agents/autonomy`, and `GET /api/agents/sessions` are the human-review surfaces.
- **I3 kill-switch** — the loop is gated default-off. The scheduled workflow no-ops unless the repo opts in (a `vars.EVOLVE_CLAUDE_ENABLED` flag), mirroring `AUTONOMY_ENABLED`.
- **I5 propose-only tests** — autonomy-authored tests still land as `*.proposed.py @pytest.mark.skip` and are `py_compile` + `--collect-only` validated before any PR opens.
- **Stop conditions are binding** — the loop halts and surfaces to a human on any OPEN QUESTION touching licensing, a new data source, a model swap, a destructive migration, or removal of a HITL gate; on any change needing a constitution amendment; or after 3 saturation cycles.

**Credential boundary.** The workflow authenticates Claude Code with a CI secret (`CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`). This is **dev-time only** — it edits the repo; it is never wired into a product-runtime code path (§1). The product runtime stays Ollama / local-first.

### 2. Narrow auto-merge class **AM-1** (amends §10, §12 I1)

§12 I1 ("no auto-merge") is amended to carve exactly **one** class. A change may auto-merge **only if every condition holds**:

1. **Scope:** the entire diff is the removal of a `@pytest.mark.skip("autonomy-proposed")` decorator (and any now-dead skip import) from one or more `*.proposed.py` files — i.e. promoting an autonomy-proposed test from skipped to live. **No non-test file may change.**
2. **Green:** the full `make test` + `make lint` + `make typecheck` + `spec_validator` + `backlog_lint` gates pass on the PR head, and the newly-un-skipped tests are the ones that ran (not skipped).
3. **Provenance:** the PR was opened by the autonomy surface, carries the `autonomy` + `auto-merge:AM-1` labels, and links its `SessionRun`.
4. **Mechanism:** a dedicated workflow with `contents: write` performs the squash-merge; it asserts conditions 1–3 first and refuses otherwise. **No other workflow is granted merge permission.**

Everything outside AM-1 remains **draft-PR-only, human-approved** (Level 2). This promotes the repo to **Level 2.5** for AM-1 alone; full Level 3 still requires a further ADR.

**Implementation is deferred and gated on this ADR's acceptance.** WS2 ships the evolve loop ending in **draft** PRs only; the AM-1 auto-merge workflow is a tracked follow-up (`BL-20260615-06`) built once this ADR is merged.

## Consequences

- Continuous, unattended repo improvement becomes possible through Claude Code, not just Copilot, while preserving every ADR-0003 invariant and the HITL gates.
- One tightly-bounded, low-blast-radius class (live-ifying a passing proposed test) can flow without a human click, reducing review toil; everything substantive still gets human eyes.
- A new failure mode — a green-but-undesirable proposed test auto-merging — is bounded by condition 1 (test-only diff) and recoverable by reverting one commit. The `auto-merge:AM-1` label makes such merges trivially auditable and revertible.
- Operators must manage a CI credential for Claude Code; documented in [docs/claude-code-autonomous-guide.md](../claude-code-autonomous-guide.md).

## Alternatives Considered

- **Strict draft-PR-only forever (status quo §12 I1).** Safest, but the maintainer chose to reduce toil on the trivial proposed-test class.
- **Celery `--kind evolve` pillar.** Rejected: the evolve loop opens *code* PRs and belongs in the Claude Code / GitHub Actions surface, not the data-ingestion Celery pillars. The Celery pillars (TestPilot, CorpusGrowth) keep their ADR-0003 scope.
- **Full Level 3 (broad auto-merge).** Rejected as premature; AM-1 is the minimal viable carve-out and a deliberately reversible experiment.

## Supersedes / Superseded by

Amends — does not supersede — [ADR 0003](0003-autonomy-orchestrator.md) (extends its invariants to the Claude Code surface). Not superseded.
