---
name: ux-review
description: Run one repeatable UI/UX and navigation review pass over the Law AI app shell — score the rubric, fix the single worst finding, and promote the fix into the mechanical gate. Use when asked to review, audit, or improve the UI/UX, navigation, scrolling, layout, responsiveness, or accessibility of the frontend, or when running /ux-review on a loop.
---

One pass of the Law AI UI/UX review loop. The contract is [docs/ui-ux-review.md](../../../docs/ui-ux-review.md) — read it before acting; this file is the operating procedure, that file is the rubric.

A pass ends in **one merged improvement**, never a list of complaints. If you finish a pass having only written findings down, the pass failed.

## Ground rules

- Docker-first. Every test/lint/typecheck runs through `make` ([CLAUDE.md](../../../CLAUDE.md)). The three host-stdlib gates (`scripts/ux_audit.py`, `scripts/spec_validator.py`, `scripts/backlog_lint.py`) are the only exceptions.
- Presentation, not product. Changing what the app claims about legal authority, weakening a UPL disclaimer, HITL gate, or provenance surface, adding a runtime npm dependency, or redesigning a feature's information model are **stop conditions** — surface them to a human instead.
- No new dependencies. The shell is first-party on purpose (spec 039 ADR 0006).

## Procedure

### 1. Orient

```bash
git log --oneline -20 -- frontend/
```

Read the pass log at the bottom of [docs/ui-ux-review.md](../../../docs/ui-ux-review.md) so this pass starts where the last one stopped, and skim [docs/ui-ux.md](../../../docs/ui-ux.md) for the current inventory. New functionality since the last pass is where new gaps are.

### 2. Run the mechanical floor

```bash
make ux-audit
make test-frontend
```

If `ux-audit` is red, fixing it **is** this pass — stop here and do that. A structural regression outranks any judgement call.

### 3. Score the rubric

Score D1–D8 from [docs/ui-ux-review.md](../../../docs/ui-ux-review.md) at 0–3 over the routes that exist today. Cite a file and line for every score below 3 — a score with no evidence is an opinion. Remember that 2 means "every current screen does it" and 3 means "the next screen cannot get it wrong"; the gap between them is the whole point of the loop.

Report the scores as a short table before you touch code.

### 4. Fix exactly one thing

Take the lowest dimension; break ties by safety (D8) first, then first-run path, then blast radius. Scope it so it lands in one reviewable diff.

- Non-trivial → run the AO-SDLC chain (`/specify → /clarify → /plan → /tasks → /implement`) and write the spec package under `specs/NNN-slug/`.
- One-file fix → skip the spec package, keep every gate.

Compose the existing primitives rather than adding new ones: `PageLayout`, `StickyToolbar`, `Drawer`, `useShellScroll`, `.shell-scroll`, `.shell-panel-scroll`, `.focus-ring`, the `--z-*` scale. Register new destinations in `frontend/lib/modules/catalog.ts` — never teach `AppShell.tsx` about a route.

### 5. Promote the fix into the floor

This is the step that makes the loop converge instead of cycling. If the fix could regress silently, it earns one of:

- a new rule in `scripts/ux_audit.py` (zero false positives, or it will be deleted), documented in the rule table in [docs/ui-ux-review.md](../../../docs/ui-ux-review.md);
- a test in `frontend/__tests__/shell/`;
- a shared primitive that makes the wrong thing unspellable.

### 6. Close the loop

```bash
make lint && make typecheck && make test && make lint-specs
```

Then, per constitution §11: populate `## Follow-ups Discovered` in the spec's `tasks.md`, mirror each item into [BACKLOG.md](../../../BACKLOG.md) as `BL-YYYYMMDD-NN` (`python3 scripts/next_backlog_id.py` for the next id), copy those bullets into the PR body, append a row to the pass log, and update [docs/ui-ux.md](../../../docs/ui-ux.md) if the UI changed (constitution §9).

## Running it on a loop

`/loop 1d /ux-review` is the intended cadence — often enough to catch a module while its author still remembers it, rare enough that each pass has real material. On a loop, keep pass N+1 honest: read the log first and pick a *different* dimension unless the last one is still the worst.
