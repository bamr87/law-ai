# Spec: Truthful Agent Harness + Resilient Dev Substrate

- **ID**: 026-truthful-harness-dev-substrate
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-10
- **Roadmap Epic**: continuous-evolution hardening (repo-wide audit 2026-08-10)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §4 (provenance), §11 (continuous evolution), §12 (autonomy invariants), §13 (jurisprudential honesty)

## 1. Problem & Motivation

A seven-subsystem audit (2026-08-10) found the flagship analysis path violating the constitution's honesty rules: the default `POST /api/analysis` returned a **hardcoded negligence IRAC at confidence 0.82** plus a **fabricated precedent** ("Smith v. Jones", 0.88, "Found 12 highly relevant precedents"), averaged to 0.85 — clearing the HITL threshold so fabricated legal content shipped **without human review**, logged to the audit trail under real model names. Related integrity holes: `log_agent_call` used Python's salted `hash()` (irreproducible audit hashes), `logged_node` hashed the class instance instead of the workflow state, the LangGraph refusal path reported "citations verified", unverified citations were stripped before reviewers saw them, and the autonomy loop silently no-opped in CI (`AUTONOMY_ENABLED` never set; proposals written to `backend/backend/…` where nothing read them). The dev substrate raced its databases at boot, shipped a ~1 GB frontend build context, recommended a constitutionally forbidden AI extension, and made server-side frontend breakpoints unbindable.

## 2. Goals

- G1: The analysis surface never fabricates legal content; unimplemented paths say so
(degraded, confidence 0.0) and always require human review (BL-20260803-02 partially addressed: retrieval coverage envelope; claims that item's retrieval-tool half).
- G2: Audit-trail hashes are reproducible and hash the actual inputs (§4).
- G3: The autonomy/evolution loop actually runs in CI and its artifacts land where
  reviewers and CI look (§12 I4/I5).
- G4: The Docker dev/test substrate is race-free, reproducible, and bounded; VS Code
  run/debug works end-to-end for all three services.
- G5: Dev-time MCP servers give sanctioned agents direct introspection of the local
  stack without touching the product runtime (§1).

## 3. Non-Goals

- NG1: Real GraphRAG retrieval implementation (stays BL-20260502-04).
- NG2: New data-source adapters (each needs its own `/specify` cycle per §12 I2);
  this spec only documents candidates in `docs/data-sources.md`.
- NG3: Frontend rendering of the new coverage envelope / verified flags (follow-up).
- NG4: Devcontainer + host-toolchain-free editor IntelliSense (follow-up).

## 4. User Stories

- As a lawyer reviewing Analysis Studio output, I want unimplemented paths to say so
  explicitly, so that I never mistake placeholder text for legal analysis.
- As a reviewer, I want every citation shown with its verification status, so that
  hallucination-flagged citations are inspectable instead of silently dropped.
- As a maintainer, I want audit hashes reproducible across restarts, so that the
  provenance trail can actually prove what an agent saw.
- As a developer, I want `make dev`/`make debug` to come up deterministically with
  attachable debuggers, so that I can fix issues instead of fighting the stack.

## 5. Functional Requirements

- **FR-1**: `PrecedentHunter.run` returns zero precedents, `confidence=0.0`,
`degraded=true`, and a summary stating no retrieval ran; the provenance event uses model label `degraded/not-implemented`, never a real model id.
- **FR-2**: `LegalAnalyst._run_legacy` returns a degraded refusal (no fabricated IRAC,
`confidence=0.0`, `degraded=true`, `requires_review=true`) logged as `degraded/not-implemented`.
- **FR-3**: `/api/analysis` excludes degraded agents from the confidence mean and
forces `requires_human_review=true` when any agent is degraded or flags review; the HITL flag is a structured field, not prose string-matching.
- **FR-4**: `LegalWorkflow` emits a retrieval coverage envelope
(`retrieval_stats`: queries, result_count, jurisdiction_requested, coverage_note) distinguishing "no results in our corpus" from "no such law" (§13), surfaced through `IRACOutput.retrieval`.
- **FR-5**: `_cite_check` sets `human_approval_required=true` when there are zero
citations; the LangGraph conclusion reports refusal / N-unverified / N-verified states truthfully and keeps unverified citations in `sources` with a `verified` flag.
- **FR-6**: `_analyze`/`_retrieve` survive malformed LLM output shapes (JSON arrays,
  non-dict citations, non-numeric confidence) by degrading to the refusal default.
- **FR-7**: `log_agent_call` uses the deterministic `_stable_hash`; `logged_node`
hashes the state argument (never `self`); WS delivery bookkeeping is logged under a distinct event type (`ws_event_sent`), not `agent_call`.
- **FR-8**: `TestSynthesizer._PROPOSED_DIR` is anchored to the backend package root;
  nightly CI sets `AUTONOMY_ENABLED=True` on the synthesis step.
- **FR-9**: docker-compose gates app services on database health
(`condition: service_healthy`), adds healthchecks for backend/frontend/ollama/ phoenix, pins `ollama` and `phoenix` image tags, bounds neo4j/ollama memory, plumbs the root `.env` via `env_file` (optional), and gives the worker `OLLAMA_BASE_URL`.
- **FR-10**: `docker-compose.debug.yml` preserves worker semantics
(`--beat -Q autonomy,celery`) and propagates the Node inspector via `NODE_OPTIONS` so Next.js server-side breakpoints bind (port 9230).
- **FR-11**: `.dockerignore` files exclude host `node_modules`/caches from both
  build contexts; the backend Dockerfile uses a BuildKit pip cache mount.
- **FR-12**: VS Code config drops the forbidden `continue.continue` recommendation
(moved to `unwantedRecommendations`), removes the invalid `$pytest` matcher and deprecated ruff/black arg overrides, and adds tasks for single-test runs, evolve audit, autonomy dry-run, LSAT export, and agent demos; `launch.json` matches the debug ports.
- **FR-13**: Project `.mcp.json` provides dev-time Postgres (read-only) and Neo4j
Cypher MCP servers against the compose stack, documented in AGENTS.md as dev-tooling only.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: All new/changed logging goes through `law_ai.core.provenance`;
  no fabricated output may be attributed to a real model name.
- **NFR-SEC-1**: No secrets added; `.mcp.json` contains only local dev-default
  credentials; `.env` stays uncommitted (`env_file` marked optional).
- **NFR-DX-1**: `make test-backend` (with DBs up), `make lint`, `make typecheck`
  all pass in containers after the change.

## 7. Data Model Impact

None. New Pydantic fields (`degraded`, `requires_review`, `retrieval`, `retrieval_stats`, `verified` on source dicts) are additive API-response fields; no Neo4j/Postgres schema change.

## 8. API Surface

`POST /api/analysis` response is additive-extended: `irac.degraded`, `irac.requires_review`, `irac.retrieval` (coverage envelope), `precedents.degraded`, and `verified`/`resolved_case_id` keys on `irac.sources` entries. No route changes; no breaking removals.

## 9. Agent / Crew Impact

`PrecedentHunter`, `LegalAnalyst` (all three paths), `LegalWorkflow` (retrieve/analyze/cite_check nodes), `TestSynthesizer` (output location). No new agents. No prompt-template changes.

## 10. Acceptance Criteria

- **AC-1**: Given the default `/api/analysis` path, the response has
`confidence == 0.0`, `requires_human_review == true`, empty precedents with `degraded == true`, and no fabricated sources.
- **AC-2**: Given a LangGraph run with empty retrieval, the output has
`human_approval_required == true`, `retrieval_stats.result_count == 0`, and a coverage note stating absence-in-corpus ≠ absence-of-law.
- **AC-3**: Given two `logged_node` invocations on different instances with the
same state, both audit events carry the identical `input_hash == _stable_hash(state)`; `log_agent_call` events likewise.
- **AC-4**: Given an LLM response that is a JSON array or has junk citation
entries or non-numeric confidence, the workflow completes with the refusal default instead of raising.
- **AC-5**: `docker compose config` is valid; `docker compose up -d postgres
redis neo4j --wait` reaches healthy; the debug override keeps `--beat -Q autonomy,celery` on the worker.
- **AC-6**: `TestSynthesizer._PROPOSED_DIR` is absolute, ends in
  `tests/autonomy/proposed`, and contains no `backend/backend` segment.

## 11. LegalBench Impact

- Tasks affected: none (no reasoning-prompt changes; honesty labels only).
- Expected delta: 0 pp. The eval harness itself is unchanged.

## 12. Risks & Open Questions

- **R-1**: Downstream consumers relying on the fabricated default-path output will
now see a degraded refusal — this is intended (the old behavior was a constitution violation), and the frontend already renders confidence/HITL flags.
- **R-2**: Pinned `ollama`/`phoenix` tags can go stale; bumping is now a deliberate,
  reviewable act instead of a silent drift.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as BL-20260810-01 … BL-20260810-12).
