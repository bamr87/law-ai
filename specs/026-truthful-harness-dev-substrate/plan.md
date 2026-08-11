# Plan: Truthful Agent Harness + Resilient Dev Substrate

- **Spec**: [spec.md](spec.md) (026-truthful-harness-dev-substrate)
- **Approach**: single implementation cycle, four independent workstreams, each
  verifiable in isolation; backend changes are additive to API shapes so the
  frontend keeps working untouched.

## Workstream A — Harness truthfulness (FR-1 … FR-6)

1. `agents_runtime/crews/precedent_hunter.py`: replace the fabricated result
   with an empty, degraded, confidence-0.0 output; add `degraded` to
   `PrecedentList`; log as `degraded/not-implemented`.
2. `agents_runtime/crews/legal_analyst.py`:
   - `IRACOutput` gains `degraded`, `requires_review`, `retrieval` (additive).
   - `_run_legacy` → honest degraded refusal (no mock IRAC).
   - `_run_via_claude_code` → `requires_review=true` (authorities ungrounded);
     offline fallback marked `degraded`.
   - `_run_via_langgraph` → keep ALL citations with `verified`/
     `resolved_case_id`; three-state conclusion (refusal / N unverified /
     N verified); pass through `retrieval_stats`.
3. `agents_runtime/graphs/legal_workflow.py`:
   - New `RetrievalStats` model; populate from final state in `invoke`.
   - `_parse_json` returns dicts only; `_clamp01` for confidences;
     `_retrieve`/`_analyze` tolerate malformed shapes (FR-6).
   - `_cite_check`: zero citations ⇒ `human_approval_required=true`.
4. `analysis/urls.py`: degraded-aware confidence mean; structured HITL flag;
   WS bookkeeping via new `provenance.log_event` (distinct event type).

## Workstream B — Provenance integrity (FR-7)

- `core/provenance.py`: `log_agent_call` → `_stable_hash`; optional
  `prompt_id`/`prompt_version` kwargs; `_pick_state` helper so `logged_node`
  hashes the state (first Mapping arg), never the bound instance; add
  `log_event` for non-agent events.

## Workstream C — Loops (FR-8)

- `agents_runtime/crews/test_synthesizer.py`: `_PROPOSED_DIR` anchored via
  `Path(__file__).resolve().parents[3]`.
- `.github/workflows/nightly-tests.yml`: `AUTONOMY_ENABLED: "True"` env on the
  synthesis step (kill-switch stays default-off everywhere else, §12 I3).

## Workstream D — Dev substrate (FR-9 … FR-13)

- `docker-compose.yml`: healthchecks (backend `/health`, frontend wget, ollama
  `ollama list`, phoenix stdlib urllib), healthcheck-gated `depends_on`,
  `env_file` (optional root `.env`), pinned `ollama/ollama:0.12.6` +
  `arizephoenix/phoenix:12.9.0` (tags verified against the registry),
  `mem_limit` + Neo4j heap/pagecache bounds, restart policies, worker
  `OLLAMA_BASE_URL`.
- `docker-compose.debug.yml`: worker command parity; frontend
  `NODE_OPTIONS=--inspect` + ports 9229–9231.
- `backend/.dockerignore`, `frontend/.dockerignore`; backend Dockerfile
  BuildKit pip cache mount + realistic healthcheck start period.
- `Makefile`: `test-integration` trap `down` → `stop <dbs>` (stops clobbering a
  running dev stack).
- `.vscode/`: extensions (drop forbidden Continue.dev → `unwantedRecommendations`,
  add debugpy + Claude Code, drop bogus Neo4j id), tasks (valid matchers, new
  single-test/evolve/autonomy/LSAT/demo tasks + prompt inputs), launch (frontend
  server attach 9230, accurate header), settings (no deprecated arg overrides,
  no phantom venv interpreter, osx terminal env).
- `.claude/hooks/session-start.sh`: portable Docker-daemon probe (macOS has no
  `timeout`).
- `.mcp.json` + AGENTS.md § Development Orchestration note; stale
  `backend/lawgraph/` pycache tree removed; CLAUDE.md `tools/` drift fixed;
  `docs/data-sources.md` CAP-bulk correction + eCFR/USC/RECAP candidates.

## Test strategy

- Update: `tests/api/test_analysis.py` (honest default path, threshold branch),
  `tests/agents/test_legal_analyst.py` (degraded default), 
  `tests/agents/graphs/test_legal_workflow.py` (refusal requires review,
  coverage envelope, malformed-shape survival).
- New: provenance stable-hash + bound-method state tests, `log_event` type
  test, `_PROPOSED_DIR` anchoring regression test.
- Gates: `make test-backend` (with DB services up), `make lint`,
  `make typecheck`, `make lint-specs`, `docker compose config --quiet`.

## Rollback

Every change is a normal git revert; no migrations, no data changes. Image pins
can be reverted independently of code.
