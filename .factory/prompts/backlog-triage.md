---
title: Backlog Triage
description: Verify open BACKLOG items against the actual code and open one reconciliation PR.
model_hint: claude-sonnet-5-5
inputs: REPO
obligations_note: Opens exactly one PR; never merges. Append-only — items move to Done, never deleted.
---

# Backlog Triage

You reconcile [BACKLOG.md](../../BACKLOG.md) against reality, as a compiled GitFactory line (see `.factory/backlog-triage.blueprint.json`). One run = one reviewable PR. You never merge.

## Procedure

1. Read the triage contract in [.claude/agents/backlog-triager.md](../../.claude/agents/backlog-triager.md) — its verdicts (**done / obsolete / duplicate / keep-open / needs-human**) and its evidence bar are binding: never mark done/obsolete/duplicate without a concrete artifact (file/symbol/spec); when unsure, keep-open.
2. Work through `## Open` (oldest first; also flag anything unclaimed > 60 days per the file's own triage rules). Verify each item with Read/Glob/Grep against the code and `specs/`.
3. Apply verdicts by EDITING the file, preserving the append-only audit rule: done/obsolete/duplicate items MOVE to `## Done` with `**(resolved YYYY-MM-DD)**:` or `**(resolved YYYY-MM-DD · consolidated)**:` notes, evidence, and `_Shipped in:_` / `_Deduped in:_` tails; keep the exact bullet grammar (`- **BL-YYYYMMDD-NN** — *kind, severity* — …`); NEVER delete a bullet, never renumber, never touch `## Claimed` items (they belong to their spec).
4. Keep-open items with stale wording may be sharpened in place; needs-human items get a trailing `_Triage note: needs-human — <why>._`
5. Before opening the PR, run your two granted verification commands — `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py` — and fix forward until both exit 0 (CI re-runs them on the PR as the final arbiter).

## Output

Exactly one PR on a `factory/triage-*` branch titled `chore(backlog): triage reconciliation`, whose body lists a verdict table (id → verdict → evidence) and per-verdict counts. If a dry run (PLAN mode), report the table without opening a PR.
