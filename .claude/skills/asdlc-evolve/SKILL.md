---
name: asdlc-evolve
description: Run one full autonomous AO-SDLC cycle (pick a backlog item, specify→clarify→plan→tasks→implement, ship a draft PR, close the loop). Use when asked to evolve the repo, run autopilot, pick up the next backlog item, autonomously fix issues or implement backlog work, or "advance the repo".
---

The autonomous **Evolution Pilot** for LawGraph AI: advance the repo by one full AO-SDLC cycle without a human picking the work. The full runbook is [prompts/evolve.md](prompts/evolve.md) — **read it in full and follow it exactly**. This skill is the Claude Code entry point and guard rails; paths below are relative to the repo root.

## Required reading first (in order)
1. [docs/constitution.md](docs/constitution.md) — esp. §11 Continuous Evolution, §12 Autonomy Loop Invariants.
2. [AGENTS.md](AGENTS.md) · 3. [BACKLOG.md](BACKLOG.md) · 4. [README.md](README.md) / [PRD.md](PRD.md).

## Procedure (summary — authoritative detail in prompts/evolve.md)
1. **Pick** the single highest-priority `## Open` BL-* (severity → refactor-budget → oldest). If `## Open` is empty, switch to **Discovery Mode**, append ≥3 new BL-* items, restart.
2. **Sanity-check** the pick against constitution §1/§2/§4/§11.
3. **Run the chain** as Claude Code skills: `asdlc-specify` → `asdlc-clarify` → `asdlc-plan` → `asdlc-tasks` → `asdlc-implement`.
4. **Close the loop**: `tasks.md` ends with `## Follow-ups Discovered`; mirror each into `BACKLOG.md ## Open` with a fresh id (`python3 scripts/next_backlog_id.py` mints `BL-YYYYMMDD-NN`); move the claimed item to `## Done` with the PR link.
5. **Verify gates** (all exit 0): `python3 scripts/spec_validator.py`, `python3 scripts/backlog_lint.py`, `make test-backend`, `make test-coverage`.

## Claude Code execution path (vs Copilot)
- **End in a DRAFT PR — never auto-merge** (constitution §12 I1). Create a branch, commit, `gh pr create --draft`. The draft PR + the daily digest (`AUTONOMY_DIGEST_DIR`) + `GET /api/agents/autonomy` are the human review surfaces.
- All dev/test/lint runs **in Docker via `make`** — the `.claude/settings.json` hook blocks host `pytest`/`ruff`/`mypy`/`npm`/`pip`/`manage.py`.
- For parallel cycles, pick **N non-overlapping** BL-* items (different files) and spawn one Agent per item with its own BL-* id; serialize the final `BACKLOG.md` edits to avoid conflicts.

## Stop conditions — surface to a human, do not proceed
Any OPEN QUESTION touching licensing, a new external data source, a model swap, a destructive schema migration, or removal of a HITL gate; any change needing a constitution amendment; coverage that can't stay ≥65% without deleting tests; or 3 consecutive cycles with zero net-new BACKLOG items (saturation).

## Output
Print the exact "Evolution cycle complete" block from [prompts/evolve.md](prompts/evolve.md) §Output.
