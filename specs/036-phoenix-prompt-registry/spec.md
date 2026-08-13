# Spec: Phoenix Prompt Registry & Sync

- **ID**: 036-phoenix-prompt-registry
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: observability — align prompt assets with the Arize Phoenix surface shipped in spec 010
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — no new vendor (Phoenix is already self-hosted in the stack), no new Python dependency, provenance logging preserved (§"Non-negotiables"), files remain the canonical prompt source so `LLM_PROVIDER_CHAIN=ollama` local-only deployments are unaffected.

## 1. Problem & Motivation

Spec 010 put a self-hosted Arize Phoenix container in the stack, but only the *tracing* half is wired (OTEL collector + trace deep-links). The *prompt management* half of Phoenix is unused: every prompt the product runs lives as a loose markdown file (`backend/law_ai/agents_runtime/prompts/*.v<N>.md`, `legal_workflow/*.md`) plus the AO-SDLC prompt chain at the repo root (`prompts/*.md`), and each consumer hard-codes its own path + version constant. Nothing makes those prompts visible, versioned, or comparable inside the application's observability surface — a Phoenix trace shows an LLM span, but the prompt it references cannot be looked up in Phoenix.

Aligning the prompt directories with Phoenix's Prompt Management API makes every prompt accessible through the application stack (Phoenix UI at `PHOENIX_UI_URL`, REST at `/v1/prompts`), with file versions mapped to Phoenix version tags.

## 2. Goals

- G1: One registry module that enumerates every local prompt template (runtime + AO-SDLC) with a Phoenix-safe identifier, version, and content hash.
- G2: An idempotent, one-command sync that mirrors those files into Phoenix Prompt Management (create prompt, create version, tag `v<N>`).
- G3: Keep files as the single source of truth — sync is one-way (repo → Phoenix); Phoenix edits never flow back.

## 3. Non-Goals

- NG1: Runtime prompt loading *from* Phoenix (fetch-with-fallback). Consumers keep reading files; recorded as a follow-up.
- NG2: Syncing LegalBench/eval prompt fixtures — the eval harness stays pinned and self-contained.
- NG3: Two-way sync or editing prompts in the Phoenix UI as an authoring surface.
- NG4: Automatic sync on app startup — the sync is an explicit operator command.

## 4. User Stories

- As an operator, I want `make sync-prompts` to publish every repo prompt to the self-hosted Phoenix, so that I can browse and diff prompt versions in the same UI where traces land.
- As a developer, I want re-running the sync after editing a prompt file to create exactly one new Phoenix version (and move its tag), so the Phoenix history mirrors the file history without duplicates.
- As an auditor, I want each sync run recorded through `core.provenance`, so prompt publication is part of the audit trail.

## 5. Functional Requirements

- **FR-1**: A registry module (`law_ai.agents_runtime.prompts.registry`) discovers all runtime prompts: `backend/law_ai/agents_runtime/prompts/<name>.v<N>.md` (versioned) and `backend/law_ai/agents_runtime/prompts/legal_workflow/<node>.md` (mapped to `legal_workflow_<node>`, unversioned). Each entry exposes: Phoenix-safe `name` (matching `^[a-z0-9]([_a-z0-9-]*[a-z0-9])?$`), optional integer `version`, file path, text, and sha256 content hash.
- **FR-2**: The registry also discovers the AO-SDLC dev-prompt chain at the repo root (`prompts/*.md`, host path or the `/repo` container mount), published under an `sdlc_` name prefix. A missing directory is tolerated (empty family, no error).
- **FR-3**: `sync_prompts()` mirrors registry entries into Phoenix via its REST API (`POST /v1/prompts`, `POST /v1/prompt_versions/{id}/tags`, `GET /v1/prompts/{id}/latest`, `GET /v1/prompts/{id}/tags/{tag}`). Idempotent: unchanged content → no new version; changed content → exactly one new version (tag `v<N>` re-pointed for versioned prompts). Phoenix 12.9.0 accepts only `CHAT` templates, so each file is published as a single `system` message with `template_format: NONE`.
- **FR-4**: A Django management command `sync_prompts` (with `--dry-run` and `--base-url`) runs the sync and exits non-zero on any per-prompt failure; a `make sync-prompts` target wraps it Docker-first.
- **FR-5**: Phoenix connectivity is configured by `PHOENIX_BASE_URL` (new env/setting); when unset it is derived from `PHOENIX_COLLECTOR_ENDPOINT` by stripping the `/v1/traces` suffix. With neither set, the command fails with a clear error and the sync module is inert.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: All Phoenix HTTP goes through `httpx` with explicit timeout and transport retries; no new third-party dependency is added.
- **NFR-AUDIT-1**: Every sync run logs a `prompt_sync` event via `core.provenance.ProvenanceLogger.log_event` with per-prompt outcomes (created / updated / skipped / error) and content hashes.
- **NFR-TEST-1**: Registry and sync are unit-tested without a live Phoenix (respx-mocked HTTP); tests run under the standard `make test-backend` marker set.

## 7. Data Model Impact

None. No Neo4j/Postgres schema changes; the only new persisted artifacts are audit `prompt_sync` events through the existing provenance path and prompt records inside Phoenix's own volume.

## 8. API Surface

No new HTTP routes in the Django backend. The prompts become accessible through the application stack via Phoenix's existing surface: UI at `PHOENIX_UI_URL` → Prompts, REST at `GET /v1/prompts`, `GET /v1/prompts/{identifier}/latest`, `GET /v1/prompts/{identifier}/tags/{tag}`.

## 9. Agent / Crew Impact

No agent behavior changes. Consumers (`lsat_content_author`, `test_synthesizer`, `topic_frontier`, `LegalWorkflow`) keep loading their prompt files directly; the registry is additive. Migrating them onto the registry is a recorded follow-up.

## 10. Acceptance Criteria

- **AC-1**: Given a clean Phoenix, when `sync_prompts` runs, then every registry prompt exists in Phoenix, versioned files carry their `v<N>` tag, and `GET /v1/prompts/{identifier}/tags/v<N>` returns the exact file content.
- **AC-2**: Given an already-synced Phoenix, when `sync_prompts` runs again with unchanged files, then zero new prompt versions are created (all outcomes `skipped`).
- **AC-3**: Given one edited prompt file, when `sync_prompts` runs, then exactly one new Phoenix version is created and its `v<N>` tag (when versioned) points at the new version.
- **AC-4**: Given `PHOENIX_BASE_URL` and `PHOENIX_COLLECTOR_ENDPOINT` both unset, when the command runs, then it exits non-zero with an actionable message and performs no HTTP calls.
- **AC-5**: A `prompt_sync` provenance event is written for every non-dry run, and `--dry-run` performs no writes (neither HTTP POSTs nor audit events).

## 11. LegalBench Impact

None — the LegalBench harness and its prompts are explicitly out of scope (NG2) and remain pinned to Ollama.
