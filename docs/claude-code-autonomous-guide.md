# Claude Code autonomous-runs guide

How to run — and safely operate — the unattended Claude Code evolve loop. Governed by [docs/constitution.md](constitution.md) §11/§12/§13 and [docs/adr/0004-claude-autonomy-surface.md](adr/0004-claude-autonomy-surface.md). For the lifecycle skills themselves, see [CLAUDE.md](../CLAUDE.md) § "Autonomous runs".

## What "autonomous" means here

| Mode | Trigger | Ends in | Human approval |
|---|---|---|---|
| **Attended** | A human runs `/asdlc-evolve` in Claude Code | a **draft** PR | required to merge |
| **Unattended** | [.github/workflows/evolve-claude.yml](../.github/workflows/evolve-claude.yml) on a schedule | a **draft** PR | required to merge |
| **Auto-merge (AM-1 only)** | a dedicated workflow, *after* ADR-0004 is accepted | a squash-merge | none — bounded to test-only un-skips (see ADR-0004 §2) |

Everything except the narrow **AM-1** class (live-ifying a passing `*.proposed.py` test) is draft-PR-only and human-approved — the repo stays **Level 2** (constitution §10).

## Turning it on

The loop is **default-off** (constitution §12 I3). To enable the scheduled Claude evolve loop on a repo:

1. Add a CI secret for Claude Code (dev-time only, **never** a product-runtime path — §1):
   - `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`), or `ANTHROPIC_API_KEY`.
2. Set repo variable `EVOLVE_CLAUDE_ENABLED=true` (the workflow no-ops otherwise — the kill-switch).
3. Optionally tune `vars.EVOLVE_CLAUDE_MAX_ITEMS` (default 1 item/run).

To stop it: unset `EVOLVE_CLAUDE_ENABLED` (or set `false`). In-flight draft PRs are harmless — close them.

## Backpressure & stop conditions (binding)

The loop MUST halt and surface to a human (never guess) on any of:

- An OPEN QUESTION touching **licensing, a new external data source, a model swap, a destructive schema migration, or removal of a HITL gate**.
- A change that would require a **constitution amendment**.
- Coverage cannot stay **≥ 65%** without deleting tests.
- **Saturation:** 3 consecutive cycles produce zero net-new BACKLOG items — ask a human for new direction.
- **Empty BACKLOG:** switch to Discovery Mode (audit → append ≥3 items), don't invent feature work.

## Review surfaces

- **Draft PRs** — labelled `evolve` / `autonomy`; the PR body copies the new BACKLOG bullets (§11).
- **Daily digest** — `AUTONOMY_DIGEST_DIR` (`backend/var/autonomy/digest-<date>.md`).
- **Dashboard** — `GET /api/agents/autonomy` (kill-switch + recent cycles), `GET /api/agents/sessions` (the change ledger: backlog → spec → PR → audit timeline), surfaced on `/agents`.

## Reviewing an autonomous PR — checklist

1. Is the claimed `BL-*` item real, and did it move `## Open` → `## Claimed`/`## Done`?
2. Does `tasks.md` end with `## Follow-ups Discovered`, mirrored into BACKLOG with fresh ids?
3. Did all gates pass **in Docker** (the loop can't run host `pytest`/`ruff` — the `.claude/settings.json` hook blocks it)?
4. Any new `*.proposed.py` tests — are they still `@pytest.mark.skip`? Un-skip only after reading them.
5. Open the `SessionRun` on the dashboard to see the full provenance timeline of the run.

## AM-1 auto-merge (after ADR-0004 acceptance)

A change auto-merges **only** when its entire diff is removing `@pytest.mark.skip("autonomy-proposed")` from `*.proposed.py` files, all gates are green, and it carries the `auto-merge:AM-1` label (ADR-0004 §2). Anything else is rejected by the merge workflow. Revert is one commit; the label makes every such merge auditable.
