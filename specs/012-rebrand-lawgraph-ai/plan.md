# Plan: Revert abortive LexGraph rebrand

- **Spec**: [spec.md](spec.md)
- **Status**: shipped (2026-05-05)

## Architecture

Mechanical revert with no runtime code changes. The Python source already imports `from lawgraph...` everywhere; only the on-disk directory name and the documentation surfaces drifted. The fix is therefore a `git mv` plus a sed sweep.

```
Pre-revert (broken)              Post-revert (working)
──────────────────              ─────────────────────
backend/lexgraph/                backend/lawgraph/
  ├── __init__.py                  ├── __init__.py
  ├── settings/                    ├── settings/    (unchanged)
  └── ...                          └── ...
                                  ↑
                   imports `from lawgraph.core...` resolve
```

## Component change list

| Surface                              | Action                                                                  | Notes |
|--------------------------------------|-------------------------------------------------------------------------|-------|
| `backend/lexgraph/` directory         | `git mv backend/lexgraph backend/lawgraph`                              | Preserves history. |
| `backend/**/__pycache__/`             | `find backend -type d -name __pycache__ -exec rm -rf {} +`              | Clear stale `lexgraph`-named byte-code. |
| `docs/`                               | sed `LexGraph` → `LawGraph`, `backend/lexgraph/` → `backend/lawgraph/`  | Includes constitution, architecture, agent-roles, data-model, data-sources, local-ai, related-github-repos, ao-sdlc, ao-sdlc-guide, legalbench, security, django-conventions. |
| `prompts/`                            | Same sed                                                                | All 8 templates. |
| `specs/_template/{spec,plan,tasks}.md`| Same sed                                                                | Future specs inherit correct brand. |
| `specs/012-rebrand-lawgraph-ai/`      | Full rewrite                                                            | spec/plan/tasks now describe the revert, not a rename to LexGraph. |
| `.github/copilot-instructions.md`     | Same sed                                                                | Path-mapping line and brand mention. |
| `.github/instructions/agents.instructions.md` | Same sed + `applyTo` glob points at `backend/lawgraph/agents_runtime/**` | |
| `AGENTS.md`, `README.md`, `PRD.md`, `BACKLOG.md`, `local-ai-plan.md` | Same sed                                                                | Header brand text + path references. |
| `backend/README.md`, `tests/README.md`| Same sed                                                                | |
| `docs/adr/0002-rebrand-lawgraph-ai.md` | New file                                                                | Records the revert decision. |
| `docs/adr/README.md`                  | Add ADR-0002 row                                                        | |
| `docs/operator-rebrand-runbook.md`    | New file                                                                | Greenfield path + recovery from broken intermediate. |

## Files explicitly NOT touched

- `backend/lawgraph/**/*.py` — already correct, every import resolves under the new directory name.
- `backend/manage.py`, `backend/pyproject.toml`, `backend/scripts/*` — already say `lawgraph`.
- `docker-compose.yml`, `.env.example`, `Makefile` — already say `lawgraph`.
- `docs/adr/0001-adopt-django-backend.md` — historical; references to pre-Django `backend/app/` stay verbatim.
- `specs/001-*` … `specs/011-*` — append-only history per [docs/constitution.md](../../docs/constitution.md) §11.
- `LexGraph_AI_Proposal.md` filename — kept for `git log --follow` history.

## Replacement map

| From                          | To                            | Scope |
|-------------------------------|-------------------------------|-------|
| `LexGraph AI`                 | `LawGraph AI`                 | All non-historical docs/prompts/specs. |
| `LexGraph` (PascalCase)       | `LawGraph`                    | Same. |
| `backend/lexgraph/`           | `backend/lawgraph/`           | Same. |
| `lexgraph.<module>` (Python dotted path) | `lawgraph.<module>`     | Same. |
| `"lexgraph"` / `'lexgraph'`   | `"lawgraph"` / `'lawgraph'`   | Same. |

## Verification

- `grep -rn "LexGraph\|backend/lexgraph" docs/ prompts/ specs/_template specs/012-rebrand-lawgraph-ai .github/ AGENTS.md README.md PRD.md BACKLOG.md backend/README.md tests/README.md local-ai-plan.md` → no matches.
- `cd backend && python -c "import lawgraph"` succeeds (with deps installed).
- `python scripts/spec_validator.py && python scripts/backlog_lint.py` exit 0.
- `pytest -q` collects without `ModuleNotFoundError`.

## Rollout

Single commit on `main`. No feature flag, no migration, no env-var change for operators on the original `.env.example`. Operators who pulled the half-rebranded state follow [docs/operator-rebrand-runbook.md](../../docs/operator-rebrand-runbook.md) §2.
