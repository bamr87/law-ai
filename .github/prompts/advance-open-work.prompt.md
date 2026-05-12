---
description: "Pick one open spec (under specs/) or GitHub issue and advance it by exactly one AO-SDLC step (clarify → plan → tasks → implement). Records follow-ups and updates BACKLOG.md per constitution §11."
name: "Advance Open Work"
argument-hint: "Optional: spec slug (e.g. 006-knowledge-graph), BL-id, or issue #N. Leave blank to auto-pick."
agent: "agent"
model: ["Claude Sonnet 4.6 (copilot)", "GPT-5 (copilot)"]
---

# Advance Open Work

You are operating on the LawGraph AI repo. Required reading: [AGENTS.md](../../AGENTS.md), [docs/constitution.md](../../docs/constitution.md) (esp. §11), [BACKLOG.md](../../BACKLOG.md).

The project's spec-driven workflow lives in [prompts/](../../prompts/): [/specify](../../prompts/specify.md), [/clarify](../../prompts/clarify.md), [/plan](../../prompts/plan.md), [/tasks](../../prompts/tasks.md), [/implement](../../prompts/implement.md). For full autopilot use [/evolve](../../prompts/evolve.md) instead — this prompt advances **one step on one item**, no further.

## Inputs

The user-supplied argument (if any) selects the target:

- `NNN-slug` (e.g. `006-knowledge-graph`) → that spec package under [specs/](../../specs/).
- `BL-YYYYMMDD-NN` → the matching backlog item in [BACKLOG.md](../../BACKLOG.md).
- `#N` or a GitHub URL → that issue (use `mcp_io_github_git_issue_read` if available; otherwise ask the user to paste the body).
- *(empty)* → auto-pick using the ordering in [/evolve](../../prompts/evolve.md) step 1.

## Procedure

1. **Identify the target.** State exactly which spec / backlog id / issue you chose and why (1–2 sentences). If auto-picking, list the top 3 candidates and the chosen one.
2. **Determine the next AO-SDLC step.** Inspect the spec directory:
   - Missing `spec.md` → run [/specify](../../prompts/specify.md).
   - Has `spec.md` with unresolved `OPEN QUESTION OQ-N` markers → run [/clarify](../../prompts/clarify.md).
   - Has `spec.md` (clarified) but no `plan.md` → run [/plan](../../prompts/plan.md).
   - Has `plan.md` but no `tasks.md` → run [/tasks](../../prompts/tasks.md).
   - Has `tasks.md` with unchecked items → run [/implement](../../prompts/implement.md) on the next unchecked task batch.
   - All tasks checked → close the loop: ensure `## Follow-ups Discovered` is populated, mirrored into `BACKLOG.md`, and the item is moved from `## Claimed` to `## Done`.
3. **Execute exactly that one step.** Do not chain into the next one. Follow the linked prompt verbatim, including its quality gates.
4. **Stop conditions** — surface to the human and halt if any apply (mirrors [/evolve](../../prompts/evolve.md) "Stop Conditions"):
   - An open question touches licensing, a new external data source, a model swap, a schema migration that drops data, or removal of a HITL gate.
   - A constitution amendment would be required.
   - Test coverage would drop below 65%.
5. **Verify gates** before reporting success (all gates run in Docker — see [AGENTS.md](../../AGENTS.md) § "Docker-First Workflow"):
   ```bash
   python3 scripts/spec_validator.py
   python3 scripts/backlog_lint.py
   ```
   If you ran `/implement`, also run `make test-backend` and `make lint`. All must exit 0. Never invoke `pytest`, `ruff`, `black`, or `mypy` directly on the host.

## Constraints

- **Never** finish an `/implement` step without appending entries to the spec's `## Follow-ups Discovered` and to [BACKLOG.md](../../BACKLOG.md) `## Open` with fresh `BL-YYYYMMDD-NN` ids (constitution §11).
- **Never** suggest closed-source LLMs for the product runtime, bypass `core.provenance` logging, or skip HITL gates.
- Keep edits scoped to the chosen target — do not opportunistically refactor unrelated code.
- If GitHub issue tooling is unavailable and the argument is an issue reference, ask the user to paste the issue body rather than guessing.

## Output (print exactly this block)

```
Advanced one step
- Target: <spec slug | BL-id | issue #N>
- Step run: /<specify|clarify|plan|tasks|implement|close>
- Files touched: <list>
- Follow-ups added: <BL-ids or "none (not an /implement step)">
- Gates: spec_validator ✓ backlog_lint ✓ [pytest ✓] [lint ✓]
- Next step for this item: /<next prompt> — re-run this prompt to continue
```
