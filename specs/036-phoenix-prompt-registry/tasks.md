# Tasks: Phoenix Prompt Registry & Sync

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@agent:<role>`.

---

## T-001 — Config: `PHOENIX_BASE_URL` setting + derivation

- **Refs**: FR-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/settings/base.py` (edit — env entry + setting)
  - `.env.example` (edit — document the variable)
- **Steps**:
  1. Add `PHOENIX_BASE_URL=(str, "")` to the env declaration block and export `PHOENIX_BASE_URL: str | None` beside the other `PHOENIX_*` settings.
  2. Derivation from `PHOENIX_COLLECTOR_ENDPOINT` (strip `/v1/traces`) lives in the sync module, not settings, so settings stay declarative.
- **Verify**: covered by the command tests (AC-4 path when both are blank).

## T-002 — Registry: discover local prompt files

- **Refs**: FR-1, FR-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/prompts/__init__.py` (new)
  - `backend/law_ai/agents_runtime/prompts/registry.py` (new)
- **Steps**:
  1. `LocalPrompt` frozen dataclass: `name`, `version: int | None`, `tag`, `family`, `path`, `text`, `sha256`, `description`.
  2. Discover `<name>.v<N>.md` (versioned runtime), `legal_workflow/<node>.md` → `legal_workflow_<node>` (unversioned), and repo-root `prompts/*.md` → `sdlc_<stem>` (unversioned; dir resolved via `LAW_AI_SDLC_PROMPTS_DIR` env override, `/repo/prompts` container mount, or the host repo root — missing dir tolerated).
  3. Sanitize names to Phoenix's identifier grammar.
- **Verify**: `docker compose run --rm backend pytest tests/agents/prompts/test_registry.py -q` passes.

## T-003 — Phoenix sync client

- **Refs**: FR-3, FR-5, NFR-SEC-1, NFR-AUDIT-1, AC-1, AC-2, AC-3, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/prompts/phoenix.py` (new)
- **Steps**:
  1. `phoenix_base_url()` — `settings.PHOENIX_BASE_URL`, else derive from `PHOENIX_COLLECTOR_ENDPOINT`, else `None`.
  2. `sync_prompts(base_url=None, dry_run=False, client=None) -> SyncReport` — per prompt: fetch existing content by tag (versioned) or `latest` (unversioned); skip when byte-identical; else `POST /v1/prompts` (CHAT template, single system message, `template_format NONE`, provider metadata derived from `LLM_PROVIDER_CHAIN`) and tag versioned prompts via `POST /v1/prompt_versions/{id}/tags`.
  3. `httpx.Client` with explicit timeout + `HTTPTransport(retries=...)`; outcomes `created|updated|skipped|error`; one `prompt_sync` provenance event per non-dry run.
- **Verify**: `docker compose run --rm backend pytest tests/agents/prompts/test_phoenix_sync.py -q` passes.

## T-004 — Management command + make target

- **Refs**: FR-4, AC-4, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/management/commands/sync_prompts.py` (new)
  - `Makefile` (edit — `sync-prompts` target + help line)
- **Steps**:
  1. Command options `--dry-run`, `--base-url`; raise `CommandError` when no base URL is resolvable or any prompt outcome is `error`; print one line per prompt + summary.
  2. `sync-prompts:` target wraps `docker compose run --rm backend python manage.py sync_prompts`.
- **Verify**: `docker compose run --rm backend pytest tests/agents/prompts/test_sync_prompts_command.py -q` passes.

## T-005 — Tests

- **Refs**: NFR-TEST-1, AC-1, AC-2, AC-3, AC-4, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/prompts/test_registry.py` (new)
  - `backend/tests/agents/prompts/test_phoenix_sync.py` (new)
  - `backend/tests/agents/prompts/test_sync_prompts_command.py` (new)
- **Steps**: per the test strategy in `plan.md` §6 (respx-mocked Phoenix; no live container needed).
- **Verify**: `docker compose run --rm backend pytest tests/agents/prompts -q` green; `make lint` + `make typecheck` clean on the new files.

## T-006 — Docs + live verification

- **Refs**: FR-4, AC-1, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `docs/architecture.md` (edit — prompt registry → Phoenix paragraph)
  - `.env.example` (edit — see T-001)
- **Steps**:
  1. Document the sync path + command in the observability section.
  2. Run `make sync-prompts` against the live stack; verify `GET /v1/prompts` lists every registry prompt and one tag fetch round-trips file content; re-run and confirm all `skipped`.
- **Verify**: live check transcript recorded in the PR description.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests (AC-1/2/3 also verified live).
- `make lint && make typecheck && make test` green; `make lint-specs` green.
- No LegalBench delta (spec §11: none — harness untouched).
- Provenance `prompt_sync` event verified in the audit log during the live check.
- **`## Follow-ups Discovered` section below populated.**

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260811-30 — feature, med — runtime prompt loading *from* Phoenix (tag fetch + local-file fallback + provenance of the serving source); today the mirror is one-way and consumers never read Phoenix.
- BL-20260811-31 — refactor, low — migrate the four hand-rolled prompt loaders (`lsat_content_author`, `test_synthesizer`, `topic_frontier`, `legal_workflow`) onto the spec-036 registry.
- BL-20260811-32 — infra, low — automatic `sync_prompts` on main (CI or post-`make dev` hook) so Phoenix can't drift between manual runs.
