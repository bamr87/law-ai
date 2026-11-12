# Tasks: Fold lawmode into law-ai

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md) · Inventory: [docs/lawmode-migration.md](../../docs/lawmode-migration.md)

## Conventions

- Implementation is done by **Claude Code** from one handoff issue per phase (hub constitution §26/§28); the planning bot writes no migration code.
- Every implementation PR is a draft, from a branch, and carries `Governed by: PRD §5.8 / LAWAI-022 / spec 057`.
- The old `lawmode/` tree is **not** modified, archived or deleted by T-001 … T-005.
- Each task: **Refs**, **Owner**, **Status**, **Files**, **Steps**, **Verify**.

## T-001 — P1: `law_ai.lawmode` app on the provider chain

- **Refs**: FR-1, FR-2, NFR-QUAL-1, NFR-DEP-1, AC-6
- **Owner**: Claude Code (handoff issue)
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lawmode/{__init__,apps,schemas,policy}.py`, `backend/law_ai/lawmode/services/{review,artifacts}.py`, `backend/law_ai/lawmode/disclaimer.md`, `backend/law_ai/settings/base.py`, `backend/tests/lawmode/`
- **Steps**: port models/config/core from `lawmode/lawmode/`; route the single-call path through `law_ai.core.llm`; add `LAWMODE_MODELS` validation (Anthropic: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` only; no OpenAI).
- **Verify**: `make lint && make typecheck && make test`; AC-6 test.

## T-002 — P2: `code_legal_review` graph, prompts, provenance, HITL

- **Refs**: FR-3, FR-4, FR-5, NFR-AUDIT-1, NFR-HITL-1, AC-2, AC-3
- **Owner**: Claude Code (handoff issue)
- **Status**: `[ ]`
- **Files**: `backend/law_ai/agents_runtime/graphs/code_legal_review.py`, `backend/law_ai/agents_runtime/prompts/lawmode/*.v1.md`, `backend/law_ai/ingestionapp/quarantine_kinds.py`, `backend/tests/lawmode/`
- **Steps**: port the eight chains onto `ChatProviderChain`; move each inline f-string prompt to a versioned file; pass `prompt_id`/`prompt_version`; add the `lawmode_finding` HITL node.
- **Verify**: AC-2, AC-3 tests; `make test`.

## T-003 — P3: research tools on httpx + tenacity

- **Refs**: FR-6, NFR-SEC-1
- **Owner**: Claude Code (handoff issue)
- **Status**: `[ ]`
- **Files**: `backend/law_ai/agents_runtime/tools/{spdx,eurlex}.py` (if kept, OQ-2), `backend/tests/lawmode/test_tools.py`
- **Steps**: reuse `ingestionapp/sources/courtlistener.py`; implement or drop SPDX/EUR-Lex on evidence; drop the Scholar stub; mocked transports only in tests.
- **Verify**: `git grep -n "import requests" backend/law_ai/lawmode backend/law_ai/agents_runtime/tools` empty; `make test`.

## T-004 — P4: `lawmode_scan` command, Make target, JSON v1, docs

- **Refs**: FR-7, NFR-SEC-2, AC-1
- **Owner**: Claude Code (handoff issue)
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lawmode/management/commands/lawmode_scan.py`, `Makefile`, `backend/law_ai/lawmode/schema/report.v1.json`, `docs/lawmode.md`, `backend/tests/lawmode/fixtures/`
- **Steps**: port `cli.py` options (`--diff`, `--jurisdiction`, `--output`, `--json`); add the `scan` entry the extension expects; document the ollama-only mode and the disclaimer.
- **Verify**: AC-1; `make lint-specs`; `make test`.

## T-005 — P5: VS Code extension under law-ai CI

- **Refs**: FR-8, FR-9, NFR-SEC-1, AC-4, AC-5
- **Owner**: Claude Code (handoff issue)
- **Status**: `[ ]`
- **Files**: `extensions/vscode-lawmode/` (OQ-3), `Makefile` (`lint`, `typecheck`, `test` gain the extension via `node:20-alpine`), `.github/workflows/ci.yml` path filters, `.gitignore` (`out/`)
- **Steps**: port `src/*.ts`; replace `child_process.exec` with `execFile` + argv; consume JSON v1; add lint/tsc/test scripts; no committed build output.
- **Verify**: AC-4, AC-5; CI green on the PR; Actions spend stays $0 (public-repo standard runners only).

## T-006 — P6: retire the old `lawmode/` tree (PROPOSAL — needs Amr's OK)

- **Refs**: FR-10, AC-7
- **Owner**: Amr decides; Claude Code implements only after Amr approves in his own words
- **Status**: `[ ]` (blocked on approval)
- **Files**: `lawmode/` (whole tree), `README.md`, `AGENTS.md` layout rows; GitHub repository `bamr87/lawmode` (archive is a settings change, so Amr does it or approves it explicitly)
- **Steps**: after P1–P5 ship and `LAWAI-022` is `shipped`, open a PR that removes or archives `lawmode/`; nothing here happens on an agent's say-so.
- **Verify**: Amr's approval comment linked in the PR; `make lint && make typecheck && make test` green.

---

## Done-When (Definition of Done)

- T-001 … T-005 `[x]`; T-006 done or explicitly deferred by Amr.
- All `AC-*` covered by passing tests.
- `make lint && make typecheck && make test` green.
- LegalBench: no change (spec §12).
- Provenance logging verified on one recorded scan.
- **`## Follow-ups Discovered` section below populated**.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI (`scripts/spec_validator.py`) checks this section exists. CI (`scripts/backlog_lint.py`) checks the BACKLOG mirror.

- BL-20261112-09 — infra, med — Retire the old `lawmode/` tree after the fold-in ships (remove or archive `lawmode/`, its inert nested workflow, the committed extension build output and `lawmode/CLAUDE.md`; archive `bamr87/lawmode`). Needs Amr's OK in his own words; spec 057 T-006.
- BL-20261112-10 — feature, low — Per-repository `.lawmode/policy.yaml` overrides for `lawmode_scan`; needs PyYAML as a direct dependency with a licence and security note (constitution §8).
- BL-20261112-11 — feature, low — Optional PR-review workflow that runs `lawmode_scan` on law-ai pull requests and posts findings after HITL approval; needs Amr's OK (pull-requests: write, hosted-provider secrets; public-repo standard runners only, $0).
- BL-20261112-12 — feature, low — Package and publish the VS Code extension (Marketplace / Open VSX) once P5 ships; publishing is an external action that needs Amr's OK.
