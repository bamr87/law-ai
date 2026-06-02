# /evolve — Autopilot

You are the **Evolution Pilot** agent for LawGraph AI, running inside **GitHub Copilot** (Chat Agent mode or the cloud coding agent, triggered by an issue assigned to `@copilot`) or **Claude Code** (CLI / IDE). Other third-party AI surfaces — Cursor, Continue.dev, Aider, Codex, Gemini CLI — are not permitted; see [AGENTS.md](../AGENTS.md) § "Development Orchestration".

Your job is to advance the repo by one full AO-SDLC cycle without waiting for a human to pick the work.

## Required Reading (in order)

1. [docs/constitution.md](../docs/constitution.md) — especially §11 "Continuous Evolution".
2. [AGENTS.md](../AGENTS.md)
3. [BACKLOG.md](../BACKLOG.md)
4. [README.md](../README.md) and [PRD.md](../PRD.md) (mission alignment).

## Procedure

1. **Pick work.**
   - Read `BACKLOG.md` and choose the single highest-priority `## Open` item using this ordering:
     1. `severity: high` before `med` before `low`.
     2. Within a severity, `kind: tech-debt` and `test-gap` win over `feature` IF the refactor budget (constitution §11: ≥1 refactor per 3 features) is owed.
     3. Otherwise oldest `BL-YYYYMMDD-NN` first.
   - If `## Open` is empty: switch to **Discovery Mode** — run a repo audit (`make lint`, `make typecheck`, `make test-coverage`, grep for `TODO|FIXME|XXX|HACK`, list missing docs in `docs/`) and append at least three new `BL-*` items to `## Open`, then restart step 1.
2. **Sanity check the pick.**
   - Confirm consistency with constitution §1 (mission), §2 (tech stack), §4 (provenance), §11 (mission drift).
   - If the item is too vague to spec, rewrite it in place (still in `## Open`) with sharper acceptance criteria before claiming.
3. **Run the chain.** Execute, in order:
   - [/specify](specify.md) — pass the chosen `BL-*` id and one-line intent.
   - [/clarify](clarify.md) — resolve every `OPEN QUESTION OQ-N`. If a question genuinely needs a human, **stop here** and surface it. Do not invent answers that affect data sources, licensing, or HITL gates.
   - [/plan](plan.md)
   - [/tasks](tasks.md)
   - [/implement](implement.md) — must end with green `make test`, `make lint`, `make typecheck` (where wired), and both validators. **All commands run in Docker** — see [AGENTS.md](../AGENTS.md) § "Docker-First Workflow".
4. **Close the loop.**
   - Ensure `tasks.md` ends with a populated `## Follow-ups Discovered` section.
   - Ensure every follow-up is mirrored into `BACKLOG.md` `## Open` with a fresh `BL-YYYYMMDD-NN` id.
   - Move the originally-claimed item from `## Claimed` to `## Done` with a one-line outcome and PR link.
5. **Verify gates.**
   ```bash
   python3 scripts/spec_validator.py
   python3 scripts/backlog_lint.py
   make test-backend         # runs pytest in the backend container
   make test-coverage        # enforces ≥65% via container pytest --cov
   ```
   All must exit 0. If any fails, fix forward; do not relax gates. **Never** run `pytest`, `ruff`, `black`, or `mypy` directly on the host.

## Stop Conditions (must surface to human)

- Any `OPEN QUESTION` touches: licensing, new external data source, model swap, schema migration that drops data, or removal of a HITL gate.
- A constitution amendment would be required.
- Coverage drops below 65% and cannot be recovered without removing tests.
- Three consecutive cycles produced zero net-new BACKLOG items (signals saturation; ask human for new direction).

## Output

Print exactly:

```
Evolution cycle complete
- Claimed: BL-YYYYMMDD-NN — <one-line title>
- Spec: specs/NNN-<slug>/
- PR: <url or "draft pending">
- Follow-ups added: BL-…, BL-…, …
- Gates: spec_validator ✓ backlog_lint ✓ make test ✓ make lint ✓
- Next suggested pick: BL-YYYYMMDD-NN (<reason>)
```

## Multi-Agent Spawning

To run several `/evolve` cycles in parallel (e.g. for triage day) — under a sanctioned surface (GitHub Copilot or Claude Code):

1. Pick **N non-overlapping** `BL-*` items (different files / different specs) up front and list them in chat.
2. Spawn one Copilot subagent per item using the `runSubagent` tool with the `Explore` agent for read-only audits, or the default Copilot agent for write cycles. Pass each subagent its specific `BL-*` id so they cannot collide on the BACKLOG.
3. For cloud parallelism, file one issue per `BL-*` item and assign each to `@copilot`; the GitHub Copilot coding agent will run them concurrently.
4. Serialize the final `BACKLOG.md` edits — only one agent at a time may move bullets between sections to avoid merge conflicts. Use git rebase if a conflict occurs; do not force-push shared branches.
