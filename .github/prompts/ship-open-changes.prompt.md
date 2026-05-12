---
description: "Review uncommitted/working-tree changes, add or update docs to cover them, push to a new branch, and open a pull request. Use when ready to ship in-progress edits as a reviewable PR."
name: "Ship Open Changes"
argument-hint: "Optional: branch name (e.g. feat/lsat-streaming) and/or 1-line PR title. Leave blank to infer from diff."
agent: "agent"
model: ["Claude Sonnet 4.6 (copilot)", "GPT-5 (copilot)"]
tools: ["search", "edit", "runCommands", "github-pull-request_create_pull_request", "mcp_io_github_git_create_pull_request"]
---

# Ship Open Changes

You are shipping the current working-tree changes on the LawGraph AI repo as a reviewable pull request. Required reading: [AGENTS.md](../../AGENTS.md) (Quality Gates), [docs/constitution.md](../../docs/constitution.md) §11 (follow-ups + BACKLOG), [BACKLOG.md](../../BACKLOG.md).

## Inputs

User argument (optional) may contain a branch name, a PR title, or both. If absent, infer both from the diff.

## Procedure

1. **Survey the changes.**
   - Run `git status --short` and `git --no-pager diff --stat` to enumerate modified/added/deleted files.
   - Run `git --no-pager diff` (and `git --no-pager diff --staged`) to read the actual edits.
   - Refuse to proceed and ask the user if the working tree is clean (nothing to ship) or contains unrelated changes spanning >1 logical concern — propose how to split.

2. **Summarize and classify.** In 3–6 bullets, describe:
   - What changed (by area: backend / frontend / docs / specs / infra / tests).
   - Why (infer from code; if unclear, ask the user one targeted question before continuing).
   - Risk level (low / medium / high) and which constitution principles are touched (privacy, auditability, HITL, open-source).

3. **Documentation pass (mandatory).** For every non-trivial change, ensure docs reflect reality. Update or create as appropriate:
   - Code changes under `backend/lawgraph/<app>/` → check the matching section of [docs/architecture.md](../../docs/architecture.md), [docs/data-model.md](../../docs/data-model.md), [docs/agent-roles.md](../../docs/agent-roles.md), or app-level `README.md`.
   - New/changed agent, crew, tool, or prompt under `backend/lawgraph/agents_runtime/` → update [docs/agent-roles.md](../../docs/agent-roles.md) and bump prompt version filenames (`*.v<N>.md`) if prompt text changed.
   - Public API surface change (`backend/lawgraph/{agentsapi,analysis,graph,lsat}/`) → update `docs/api-examples.md` (create if missing).
   - New env vars or services → update [.env.example](../../.env.example), [docker-compose.yml](../../docker-compose.yml) notes, and [README.md](../../README.md) quickstart.
   - New dependency → note rationale in the PR body and confirm OSS license compatibility (MIT/Apache/BSD/AGPL only).
   - Frontend component or route change → update [frontend/README.md](../../frontend/README.md) if user-facing flow changed.
   - Public Python functions touched → ensure docstrings + examples per AGENTS.md Coding Standards.
   - If a change is purely internal refactor with no doc impact, state that explicitly in the PR body (`Docs: n/a — internal refactor`).

4. **Quality gates (all run in Docker via `make`).** Run only the gates relevant to the diff (skip others to save time, but state which you skipped and why). Never invoke `pytest`, `ruff`, `black`, `mypy`, or `npm` directly on the host — see [AGENTS.md](../../AGENTS.md) § "Docker-First Workflow":
   - Python touched: `make lint && make test-backend`
   - Strict types touched: `make typecheck`
   - Frontend touched: `make lint && make test-frontend`
   - Specs/backlog touched: `make lint-specs` (or `python3 scripts/spec_validator.py && python3 scripts/backlog_lint.py`)
   - Reasoning logic touched: `make test-legalbench` — record delta in PR body.
   - If any gate fails, fix it before continuing. Do not push red.

5. **Backlog + follow-ups (constitution §11).** If this change closes a spec's `/implement` cycle, ensure that spec's `tasks.md` has a populated `## Follow-ups Discovered` and that each follow-up is mirrored in [BACKLOG.md](../../BACKLOG.md) as `BL-YYYYMMDD-NN`. Otherwise, add at least one backlog entry for any TODO/refactor/test-gap noticed during the diff review (or write `_none — justified: <reason>_` in the PR body).

6. **Branch + commit.**
   - Determine branch name: use the user-supplied one, else derive from the dominant change as `<type>/<slug>` where `type ∈ {feat, fix, docs, refactor, chore, test, spec}` and `slug` is kebab-case ≤40 chars. Example: `feat/lsat-streaming-trace`.
   - Refuse to push to `main` directly. If the current branch is `main`, create the new branch with `git switch -c <branch>`.
   - Stage all relevant files (`git add -A` is acceptable after step 1's review confirms no stray files; otherwise stage explicitly).
   - Commit with a Conventional Commits message: `<type>(<scope>): <subject>` ≤72 chars, plus a body listing the bullets from step 2 and any `BL-` ids touched. Do **not** add `--no-verify`.

7. **Push.** `git push -u origin <branch>`. If the remote rejects (non-fast-forward, branch exists), stop and surface the error to the user — do not force-push.

8. **Open the pull request.** Prefer `mcp_io_github_git_create_pull_request` (or `github-pull-request_create_pull_request`) targeting `main`. Title = the commit subject. Body must include:

   ```markdown
   ## Summary
   <bullets from step 2>

   ## Docs
   <files updated, or "n/a — internal refactor">

   ## Quality Gates
   - [x] ruff + black
   - [x] pytest (<N> passed, <N> skipped)
   - [ ] mypy --strict (skipped: <reason>)
   - [x] frontend lint + vitest
   - [x] spec_validator + backlog_lint
   - [ ] LegalBench (skipped: no reasoning change)

   ## Backlog / Follow-ups
   - BL-YYYYMMDD-NN: <one-line>
   <or> _none — justified: <reason>_

   ## Risk
   <low|medium|high> — <one sentence>

   ## Constitution Touchpoints
   <list any of: open-source, privacy, auditability, HITL, legal accuracy — with one-line justification each, or "none">
   ```

   Mark as **draft** if any quality gate was skipped without justification, if HITL is touched, or if risk is high.

## Output

Finish with a single block containing:

- The branch name and PR URL.
- Pass/skip status for each quality gate.
- The list of `BL-` ids added or referenced.
- Any blockers the reviewer should resolve before merge.

## Hard Rules

- **Never** force-push, never `--no-verify`, never push to `main`.
- **Never** ship without the docs pass — even a one-line `Docs: n/a — internal refactor` in the PR body counts as the explicit decision.
- **Never** bypass `core.provenance` logging or HITL gates as part of "cleanup".
- If the diff includes secrets, credentials, large binaries, or generated artifacts that don't belong in git, **stop** and ask the user how to proceed.
