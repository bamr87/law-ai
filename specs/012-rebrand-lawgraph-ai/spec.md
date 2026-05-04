# Spec: Rebrand from LexGraph AI to LawGraph AI

- **ID**: 012-rebrand-lawgraph-ai
- **Status**: draft (awaiting `/clarify` — see § 13 Open Decisions)
- **Owner**: @copilot (paired with maintainer for naming + license sign-off)
- **Created**: 2026-05-03
- **Roadmap Epic**: TBD (rebrand decision request)
- **Constitution Compliance**: requires amendment — see § Constitution Impact

## 1. Problem & Motivation

The product name "LexGraph AI" is being retired in favor of **"LawGraph AI"**.
The repo currently embeds the old brand in 118 tracked files spanning code,
config, docs, tests, and ops. A piecemeal rename will leave half-rebranded
artifacts (e.g. Postgres role still `lexgraph`, OTEL project still
`lexgraph`, Python package still `lexgraph/`) that erode trust and
complicate ops handover. We need a single audited cutover.

## 2. Goals

- **G1**: Every user-visible occurrence of "LexGraph" / "lexgraph" is
  replaced with "LawGraph" / "lawgraph", preserving casing intent
  (PascalCase → PascalCase, lowercase → lowercase, ALL-CAPS → ALL-CAPS).
- **G2**: The Python package directory is renamed `backend/lexgraph/` →
  `backend/lawgraph/` with all imports, settings module paths, ASGI/Celery
  app references, and test discovery updated.
- **G3**: All ops surfaces (Postgres role/db, Neo4j password env, Phoenix
  project name, Celery app name, Docker image labels, launchd plist) are
  rebranded with a documented migration path for any operator running an
  existing dev/prod stack.
- **G4**: One historical reference is preserved per artifact for
  archaeology (ADR + the original `LexGraph_AI_Proposal.md`, kept as-is
  with a header note pointing at the rename ADR).
- **G5**: All gates green after cutover: `pytest` ≥75% cov, `ruff`,
  `black`, `mypy --strict` (where wired), `npm test -- --run`,
  `scripts/spec_validator.py`, `scripts/backlog_lint.py`.

## 3. Non-Goals

- **NG1**: Renaming the GitHub repository slug (`law-ai/`) — out of scope;
  the workspace folder stays as-is. Only the *product* and *Python package*
  rebrand. (Open question OQ-1 covers this.)
- **NG2**: Changing the database **schema** (table/column names). Only the
  Postgres role and database *name* may change; ORM table names stay
  (`pending_review`, `audit_event`, etc.) so existing rows are preserved
  per the spec-011 BL-19 contract.
- **NG3**: Migrating the LangGraph checkpointer schema name
  (`langgraph.checkpoints`) — that's an upstream library convention, not a
  brand artifact.
- **NG4**: Re-issuing API tokens or rotating secrets. The `ApiToken` table
  is brand-agnostic.
- **NG5**: Frontend visual redesign. Only string content + page `<title>`
  changes; component names like `LsatLab` stay.

## 4. User Stories

- **US-1**: As a maintainer, I want the repo to consistently say "LawGraph
  AI" so that new contributors aren't confused by two brand names.
- **US-2**: As an operator running a live LexGraph stack, I want a
  documented runbook (env-var deltas, optional Postgres rename SQL) so I
  can upgrade without data loss.
- **US-3**: As an end user opening `/`, I want the page title and nav to
  read "LawGraph AI" everywhere (no half-rebranded screens).
- **US-4**: As a CI consumer, I want every existing test to pass after the
  rebrand without semantic changes (parity guarantee).

## 5. Functional Requirements

- **FR-1** *(naming taxonomy)*: A single canonical mapping is declared in
  [plan.md](plan.md) § "Replacement Map" and applied everywhere:
  `LexGraph` → `LawGraph`, `Lexgraph` → `Lawgraph`, `lexgraph` →
  `lawgraph`, `LEXGRAPH` → `LAWGRAPH`. No other variants.
- **FR-2** *(python package rename)*: `backend/lexgraph/` is renamed to
  `backend/lawgraph/`. Every `from lexgraph...` / `import lexgraph...`
  becomes `from lawgraph...` / `import lawgraph...`.
- **FR-3** *(settings + asgi + celery)*: `DJANGO_SETTINGS_MODULE`
  defaults in `manage.py`, `asgi.py`, `wsgi.py`, `celery.py`, Docker
  CMDs, the launchd plist, and `pytest.ini` are updated to
  `lawgraph.settings.*`. The Celery app name becomes `"lawgraph"`.
- **FR-4** *(infrastructure config)*:
  - `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`, the
    `DATABASE_URL` / `POSTGRES_URL` connection strings, `NEO4J_PASSWORD`
    default, `PHOENIX_PROJECT_NAME`, and any Docker volume / network /
    container labels carrying `lexgraph` are renamed.
  - The launchd plist `scripts/launchd/com.lexgraph.evolve.plist` is
    renamed to `com.lawgraph.evolve.plist` with matching label.
- **FR-5** *(historical preservation)*: `LexGraph_AI_Proposal.md` is
  renamed to `LawGraph_AI_Proposal.md` with a header note: "Originally
  authored as 'LexGraph AI'; renamed 2026-05-NN — see
  [docs/adr/0002-rebrand-lawgraph-ai.md](../docs/adr/0002-rebrand-lawgraph-ai.md)".
  All other historical brand references inside ADRs and the new ADR-2
  itself are preserved verbatim where they describe the *prior* state.
- **FR-6** *(constitution amendment)*: A new ADR
  `docs/adr/0002-rebrand-lawgraph-ai.md` is authored capturing the
  rationale, alternatives considered (keep "LexGraph", coin a third
  name), and the supersession of every brand-locked clause in the
  constitution. The constitution is edited in-place with a footnote
  pointing to ADR-2.
- **FR-7** *(spec corpus rebrand)*: All 11 existing specs (`specs/001-*`
  through `specs/011-*`) keep their *content* but are mass-rewritten to
  use "LawGraph"/`lawgraph` everywhere except in direct quotations that
  describe historical state (e.g. ADR-1 context block).
- **FR-8** *(CI workflows)*: Every workflow under `.github/workflows/`
  with brand strings (job names, env vars, comments) is updated.
- **FR-9** *(operator migration runbook)*: A new doc
  `docs/operator-rebrand-runbook.md` lists env-var renames, the optional
  Postgres role/db rename SQL (`ALTER ROLE`, `ALTER DATABASE`), Neo4j
  password rotation guidance, and a "do nothing if greenfield" path.
- **FR-10** *(memory + repo notes update)*: `/memories/repo/*.md` files
  in this workspace are updated to reflect the new brand and package
  path so the next agent cycle inherits correct context.

## 6. Non-Functional Requirements

- **NFR-PARITY-1**: Every test that passes pre-rebrand must pass
  post-rebrand with identical assertions (only import paths and brand
  strings may change).
- **NFR-COV-1**: Backend coverage stays ≥75% (currently 84.05%).
- **NFR-AUDIT-1**: Provenance + audit log shapes are unchanged. The
  `agent_version` strings stay numeric; brand text in human-facing
  fields rebranded.
- **NFR-MIGRATION-SAFETY-1**: A greenfield `make dev` works. An
  existing-data path is documented but not auto-applied (operator runs
  the runbook by hand). No automated `DROP DATABASE` step.
- **NFR-LICENSE-1**: License (MIT/AGPL — TBD per OQ-2) is preserved or
  re-stated under the new brand without changing terms.
- **NFR-DOC-1**: Every doc under `docs/` is grep-clean of the old brand
  except inside ADR-1, ADR-2, and the proposal file (historical
  references).
- **NFR-SEC-1**: No secrets are hard-coded. Default dev passwords
  (`lexgraph-dev` → `lawgraph-dev`) stay in `.env.example` only.

## 7. Data Model Impact

- **None** to the Neo4j or Postgres *schemas*. Only the Postgres
  cluster-level role and database *names* change (operator-controlled).
- The LangGraph checkpointer schema (`langgraph.checkpoints`) is
  untouched.
- All node `source`, `confidence`, `ingest_timestamp` semantics preserved.

## 8. API Surface

- **No path or response-shape changes.** `/health`, `/api/agents/...`,
  `/api/analysis/...`, `/api/graph/...`, `/api/lsat/...`,
  `/ws/agents/{run_id}` are unchanged.
- The OpenAPI / DRF browsable API title strings rebrand from "LexGraph
  AI" → "LawGraph AI".
- The `/health` JSON `service` field (if present) updates from
  `"lexgraph"` to `"lawgraph"` — flagged as a breaking string change for
  external monitors (OQ-3).

## 9. Agent / Crew Impact

- No agent logic changes. The agent module path moves from
  `lexgraph.agents_runtime.*` → `lawgraph.agents_runtime.*`.
- `BaseLexGraphAgent` (if referenced by name) is renamed to
  `BaseLawGraphAgent` everywhere. *Open question OQ-4: do we want to
  keep the class symbol stable to avoid pickled-state breaks in any
  cached LangGraph checkpoint?*
- Prompt templates under `lexgraph/agents_runtime/prompts/` move with
  the package and have brand-string sweeps applied.

## 10. Acceptance Criteria

- **AC-1**: `grep -RIn --exclude-dir={.venv,node_modules,.next,coverage,htmlcov,staticfiles,__pycache__,.mypy_cache,.pytest_cache,.ruff_cache} -E 'LexGraph|Lexgraph|lexgraph|LEXGRAPH' .` returns ONLY:
  - `LawGraph_AI_Proposal.md` (preserved historical doc with one header banner reference),
  - `docs/adr/0001-adopt-django-backend.md` (historical context),
  - `docs/adr/0002-rebrand-lawgraph-ai.md` (the rename ADR itself, which has to mention both names).
- **AC-2**: `cd backend && pytest -q` passes; coverage ≥75%.
- **AC-3**: `cd frontend && npm test -- --run` passes (5 files / 21 tests).
- **AC-4**: `python scripts/spec_validator.py` and
  `python scripts/backlog_lint.py` exit 0.
- **AC-5**: `make lint` (ruff + black + frontend lint) passes.
- **AC-6**: `docker compose up backend worker` starts cleanly against a
  fresh `pgdata` volume; daphne and celery both report ready; `/health`
  returns 200.
- **AC-7**: `DJANGO_SETTINGS_MODULE=lawgraph.settings.prod python
  manage.py check --deploy` exits 0.
- **AC-8**: Manual smoke: open `/`, `/agents` in the browser; nav,
  page title, and footer all read "LawGraph AI"; no console errors.
- **AC-9**: `docs/operator-rebrand-runbook.md` exists, lists every
  env-var rename, and contains the optional Postgres `ALTER ROLE
  lexgraph RENAME TO lawgraph` + `ALTER DATABASE lexgraph RENAME TO
  lawgraph` SQL.
- **AC-10**: `docs/adr/0002-rebrand-lawgraph-ai.md` is approved
  (HITL Level-2 gate per constitution §10) before T-016-equivalent
  cutover lands on `main`.

## 11. LegalBench Impact

- **Zero** — no reasoning logic changes. Re-run the eval task post-rebrand
  to record a 0.0 pp delta as a parity check, no more.

## 12. Constitution Impact

The constitution currently embeds the brand "LexGraph AI" in §1 (mission)
and likely §2 (tech-stack heading). ADR-2 must:

1. Cite the *exact* clauses being renamed.
2. Declare itself a "naming amendment" (no architectural change).
3. Be approved by the maintainer (HITL Level-2) before T-016 cutover.

## 13. Open Decisions (block `/plan` and beyond until resolved)

> Surface format follows [prompts/clarify.md](../../prompts/clarify.md):
> each block below is read by the Clarifier agent and rewritten with the
> human's decision before the spec advances to `clarified`. CI's
> `spec_validator.py` will FAIL while these blocks remain — that gate is
> intentional.

> [OPEN QUESTION OQ-1]: **Repo slug change.** Do we also rename the GitHub
> repository slug (today: `law-ai`) to `lawgraph-ai`? Default proposed:
> **no** — keep `law-ai` to avoid breaking external clones / CI
> integrations (NG-1). Maintainer to confirm.

> [OPEN QUESTION OQ-2]: **Name availability + clearance.** Has "LawGraph
> AI" been cleared for use across (a) trademark, (b) PyPI package name
> (`lawgraph` / `lawgraph-ai`), (c) GitHub org / handle, (d) domain
> (`lawgraph.ai` etc.)? **STOP CONDITION** per
> [prompts/evolve.md](../../prompts/evolve.md): the AI agent MUST NOT
> proceed past `/clarify` without explicit human confirmation on this
> licensing / external-name decision (constitution §11).

> [OPEN QUESTION OQ-3]: **/health API string change.** The `/health`
> JSON `service` field renames from `"lexgraph"` → `"lawgraph"`. Any
> external monitor / dashboard relying on the literal string will need
> updating. Acceptable as a clean break, or do we keep a legacy
> `aliases: ["lexgraph"]` array for one release?

> [OPEN QUESTION OQ-4]: **`BaseLexGraphAgent` symbol stability.**
> Renaming the class to `BaseLawGraphAgent` may invalidate any pickled
> LangGraph checkpoint state that captured the qualified class name.
> Confirm: do we have any long-lived checkpoints that must survive the
> rename, or is "wipe & rebuild" acceptable for dev-only data?

> [OPEN QUESTION OQ-5]: **Live operator data.** Are there any
> production / staging Postgres clusters with live `lexgraph`-named
> role/db that need an in-place rename, or is every operator on
> greenfield dev installs? Determines whether `docs/operator-rebrand-runbook.md`
> (FR-9) is required-reading or merely informational.

---

**Next step**: human reviewer answers OQ-1 through OQ-5 in-place, then
`/clarify` rewrites the blocks and unblocks `/plan`.
