# Tasks: Truthful Agent Harness + Resilient Dev Substrate

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — PrecedentHunter honest degraded output (FR-1, AC-1, NFR-AUDIT-1)
  - Empty precedents, confidence 0.0, `degraded=true`, model label
    `degraded/not-implemented`; summary states no retrieval ran and that
    absence-of-results ≠ absence-of-law.
- [x] **T-002** — LegalAnalyst degraded legacy path + review flags (FR-2, FR-3, AC-1)
  - `IRACOutput.{degraded,requires_review,retrieval}` added; `_run_legacy`
    refuses honestly; Claude path sets `requires_review=true`; offline
    fallback marked degraded.
- [x] **T-003** — LangGraph coverage envelope + truthful conclusions (FR-4, FR-5, AC-2)
  - `RetrievalStats` populated in `invoke`; `_cite_check` requires approval on
    zero citations; `_run_via_langgraph` keeps unverified citations with
    `verified` flags and reports refusal / N-unverified / N-verified.
- [x] **T-004** — LLM output-shape hardening (FR-6, AC-4)
  - `_parse_json` dict-only; `_clamp01`; junk citation entries dropped;
    non-list queries tolerated; regression tests for array/junk/non-numeric
    responses.
- [x] **T-005** — Provenance integrity (FR-7, AC-3, NFR-AUDIT-1)
  - `log_agent_call` uses `_stable_hash` + optional prompt id/version;
    `_pick_state` fixes `logged_node` hashing `self`; `log_event` gives WS
    bookkeeping its own event type (`analysis/urls.py` migrated).
- [x] **T-006** — Analysis aggregation honesty (FR-3, AC-1)
  - Degraded agents excluded from confidence mean (0.0 when none real);
    structured `requires_review`/`degraded` flags replace prose string-match.
- [x] **T-007** — Autonomy loop fixes (FR-8, AC-6)
  - `_PROPOSED_DIR` anchored to backend root (regression test);
    nightly workflow sets `AUTONOMY_ENABLED=True` on the synthesis step.
- [x] **T-008** — docker-compose hardening (FR-9, AC-5, NFR-SEC-1)
  - Healthchecks all services; healthcheck-gated depends_on; optional
    `env_file`; pinned ollama/phoenix tags; memory bounds; restart policies;
    worker `OLLAMA_BASE_URL`; verified `docker compose config` + healthy
    `up -d postgres redis neo4j --wait`.
- [x] **T-009** — Debug override parity + frontend inspector (FR-10, AC-5)
  - Worker keeps `--beat -Q autonomy,celery` under debug; frontend inspector
    via `NODE_OPTIONS` (server binds 9230); Makefile integration-test trap
    stops only the DB services instead of `down`ing the project.
- [x] **T-010** — Build hygiene (FR-11, NFR-DX-1)
  - `.dockerignore` for backend + frontend (host node_modules/caches excluded);
    BuildKit pip cache mount; healthcheck start-period matched to boot chain.
- [x] **T-011** — VS Code run/debug + extensions (FR-12, NFR-DX-1)
  - Forbidden Continue.dev recommendation removed (+`unwantedRecommendations`);
    debugpy + Claude Code extensions added; invalid `$pytest` matcher removed;
    single-test / manage.py prompt tasks, evolve-audit, autonomy dry-run,
    LSAT export, agent demo tasks; launch configs for 5678/5679/9229/9230;
    settings drop deprecated ruff/black args + phantom venv path;
    session-start hook Docker probe made portable to macOS.
- [x] **T-012** — Dev-time MCP servers + docs truth (FR-13, NFR-SEC-1)
  - `.mcp.json` (postgres read-only + neo4j cypher against compose stack);
    AGENTS.md documents the dev-only boundary; CLAUDE.md `tools/` drift fixed;
    stale `backend/lawgraph/` pycache removed; `docs/data-sources.md` CAP
    bulk-data correction + eCFR / U.S. Code / RECAP candidate rows.

## Follow-ups Discovered

- Real Neo4j GraphRAG retriever as `LegalWorkflow`'s default, logged via
  `log_graph_query`, replacing the `[]` stub (extends BL-20260502-04; the
  coverage envelope from FR-4 is ready to carry real counts).
- Render the coverage envelope + `verified` citation flags in Analysis Studio
  (frontend half of BL-20260803-02/03; backend now ships the data).
- Close the ingestion HITL loop: `PendingReview.approved` has no consumer — an
  approval must commit quarantined knowledge to Neo4j; `ENABLE_HUMAN_APPROVAL_GATES`
  is currently a dead flag.
- LegalBench: real task data + persisted baseline + CI regression gate (today
  runs score 3–7 synthetic stubs and reports land in CWD-relative paths).
- Unified resilient Ollama client (retry/backoff/timeout) shared by tutor,
  content author, factory, TopicFrontier, TestSynthesizer — reconcile with the
  PR #19 `LLMClient` rebase (BL-20260716-01).
- WS streaming rework: emit `agent_step` events DURING the run (not post-hoc)
  and authenticate the consumer; frontend subscriber.
- UPL guardrail: "not legal advice" disclaimer + review-status banner across
  Analysis Studio and LSAT surfaces.
- Reviewer identity + rationale on every HITL decision (LSAT proposals,
  future quarantine UI), written to AuditEvent.
- Devcontainer so editor IntelliSense stops depending on host installs the
  Docker-first rule forbids.
- Async-safe Postgres audit writes (SynchronousOnlyOperation currently hides
  DB persistence failures on every async agent path at debug level).
- Rate limiting / throttling on LLM-invoking endpoints (open-by-default auth +
  120 s Ollama fan-out = trivially saturable).
- Ollama healthcheck upgrade: gate on the configured model's presence, not
  just server readiness, so eval jobs can't run against a model-less server.
