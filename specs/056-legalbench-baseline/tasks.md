# Tasks: Commit the first real LegalBench baseline

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.
- Order matters: T-001..T-006 land in one harness PR **before** any baseline is recorded, because the pinned options and metadata are part of the measurement.

---

## T-001 — Pin the gate model once, in the Makefile

- **Refs**: FR-3, NFR-DOCKER-1, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `Makefile`, `tests/test_legalbench_workflows.py` (new)
- **Steps**:
  1. Add `LEGALBENCH_MODEL ?= mistral:7b-instruct-q4_K_M` next to `LEGALBENCH_SUBSETS`.
  2. Pass `--model $(LEGALBENCH_MODEL)` in `test-legalbench`, `test-legalbench-gate` and `legalbench-baseline`.
  3. Repo-level test: `make -n` of each target contains `--model mistral:7b-instruct-q4_K_M`, and `LEGALBENCH_MODEL=x make -n …` contains `--model x`.
- **Verify**: the ci.yml root-tests tier (`pytest tests/ -m "not backend and not frontend"`) passes on the PR; `make -n legalbench-baseline` shows the explicit model.

## T-002 — Pin decoding options and make timeouts honest

- **Refs**: FR-3, FR-4, FR-8, AC-6
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `backend/law_ai/eval/legalbench.py`, `backend/law_ai/settings/base.py`, `.env.example`, `backend/tests/eval/test_legalbench_measurement.py`
- **Steps**:
  1. Settings `LEGALBENCH_ITEM_TIMEOUT_S` (300), `LEGALBENCH_NUM_CTX`, `LEGALBENCH_NUM_PREDICT`, read via `settings_proxy`; document them in `.env.example`.
  2. `_call_ollama()` sends `{"temperature": 0.0, "seed": 0, "num_ctx": …, "num_predict": …}` and catches `TimeoutError`/`socket.timeout` as well as `URLError`, raising the existing `RuntimeError` so the item is counted errored.
  3. Keep `_call_ollama()` as the only transport; add a test asserting the module imports nothing from `law_ai.core.llm` (FR-4).
  4. Stub HTTP server test: a read that sleeps past the timeout yields one errored item and no traceback.
- **Verify**: `docker compose run --rm backend pytest tests/eval -q`; `make typecheck` clean (no new baseline entries).

## T-003 — Report header and baseline schema v2

- **Refs**: FR-1, FR-2, FR-5, FR-8, NFR-PERF-1, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `backend/law_ai/eval/legalbench.py`, `backend/law_ai/eval/report.py`, `backend/law_ai/eval/fetch.py`, `backend/tests/eval/test_baseline_v2.py` (new)
- **Steps**:
  1. Once per run, read `model_digest` (Ollama `/api/show`), `ollama_version` (`/api/version`); compute `manifest_sha256` from `backend/var/legalbench/manifest.json`; take `DATA_REVISION`, `PROMPT_REVISION`, `DEFAULT_MAX_ITEMS_PER_TASK` from `fetch.py`; `git_sha` from `GITHUB_SHA` or `git rev-parse` when available; `runner` from `GITHUB_ACTIONS` + `platform`.
  2. Report rows gain per-task `n`/`correct` (from `item.metadata.task`) and per-subset wall-clock seconds; report gains `item_outcomes` and `item_outcomes_sha256` (sorted JSON, indices + 0/1 only).
  3. `update_baseline()` writes `schema_version: 2` with all FR-5 fields; refuses stubs (existing), any `--limit`, and any `errored > 0`, each with a distinct message.
  4. Tests: v2 file round-trips; each refusal writes nothing and exits 1; `item_outcomes` contains no strings other than indices.
- **Verify**: `docker compose run --rm backend pytest tests/eval/test_baseline_v2.py -q`.

## T-004 — Comparability, `--require-baseline`, exit code 3

- **Refs**: FR-6, FR-7, AC-3, AC-4
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `backend/law_ai/eval/legalbench.py`, `backend/tests/eval/test_legalbench_cli.py`
- **Steps**:
  1. Extend `baseline_comparability()` with the FR-6 fields for v2 baselines; keep the v1 model+scorer check.
  2. In `_apply_gates()`, an incomparable baseline under `--check-regression` returns exit 3 (not a warning + 0); add `--require-baseline` (missing file → exit 3).
  3. Parametrised test, one case per FR-6 field → exit 3 naming the field; 1.01 pp drop → 1; exactly 1.00 pp → 0; v1 baseline + changed digest → still comparable (v1 does not record it).
  4. Update the exit-code table in the CLI `--help` text.
- **Verify**: `docker compose run --rm backend pytest tests/eval/test_legalbench_cli.py -q`.

## T-005 — Provenance fields and the baseline event

- **Refs**: FR-12, NFR-AUDIT-1, AC-10
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `backend/law_ai/eval/legalbench.py`, `backend/tests/eval/test_legalbench_measurement.py`
- **Steps**:
  1. `_emit_item_event()` adds `prompt_sha256`, `response_sha256` (raw response, before normalisation), `model_digest`, `data_revision`; `agent_version` → `law_ai.eval.legalbench.v2`.
  2. `update_baseline()` emits one `legalbench.baseline_recorded` event via `audit_jsonl.record` with the file sha256 and header.
  3. Correct the module docstring: per-item events go to the audit JSONL/`AuditEvent`, not OpenTelemetry spans.
  4. Test with a captured `record` that every item event has the fields and exactly one baseline event is written.
- **Verify**: `docker compose run --rm backend pytest tests/eval -q`.

## T-006 — Hosted baseline workflow and nightly decoupling

- **Refs**: FR-9, NFR-COST-1, NFR-PERF-1, NFR-DET-1, NFR-SEC-1, NFR-HITL-1, AC-8, AC-9
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `.github/workflows/legalbench-baseline.yml` (new), `.github/workflows/nightly-tests.yml`, `tests/test_legalbench_workflows.py`
- **Steps**:
  1. New workflow: `on: workflow_dispatch` only; `permissions: contents: read`; `runs-on: ubuntu-latest`; `timeout-minutes: 330`; steps: checkout, the nightly disk-cleanup step, build backend image, `docker compose up -d ollama postgres redis --wait`, pull `LEGALBENCH_MODEL`, `make legalbench-cache`, run A and run B (`--update-baseline` with the baseline path redirected per run, `--report` per run), compare `item_outcomes_sha256`, upload `baseline.json` + reports + `history.jsonl` (`retention-days: 90`), write a step summary (accuracies, n/scored/errored, wall-clock, header).
  2. No `secrets.` reference, no `git push`, no `gh pr`, no merge step.
  3. Nightly: the four LegalBench steps use `if: ${{ !inputs.dry_run && !cancelled() }}` so a failed coverage step no longer skips them; the pull step reads `LEGALBENCH_MODEL`. Schedule change only per OQ-5's answer.
  4. Repo-level tests parse both YAML files (stdlib text checks, no PyYAML on host) for AC-8 and AC-9.
- **Verify**: the ci.yml root-tests tier passes on the PR; `make nightly-dry-run` (act) if available; `make lint-specs`.

## T-007 — Record and commit the baseline (human-gated)

- **Refs**: FR-1, FR-2, FR-10, FR-11, NFR-DET-1, NFR-HITL-1, AC-1, AC-2, AC-11
- **Owner**: @bamr87
- **Status**: `[ ]`
- **Files**: `backend/var/legalbench/baseline.json` (new), `docs/legalbench.md`, `backend/var/legalbench/LICENSES.md`
- **Steps**:
  1. After T-001..T-006 merge: `gh workflow run legalbench-baseline.yml --ref main`; wait; confirm AC-1 in the step summary.
  2. Download the artifact; copy `baseline.json` into `backend/var/legalbench/`.
  3. Fill the `docs/legalbench.md` baseline table (scores, n, run id, runner, baseline commit SHA — the SHA is filled in a follow-up commit on the same PR once known) and remove both `_TBD_`s; add the FR-11 citation, licences, pinned revisions and each task README's source line; add the §13 note on the `precedent_retrieval` row; document exit code 3 and the re-baseline triggers (FR-10).
  4. Open the PR (draft if opened by an agent), label `no-visual-change`; Amr reviews and merges.
- **Verify**: `make test-legalbench-gate` on the hosted runner (dispatch nightly or the baseline workflow in gate mode) exits 0 with 0.00 pp deltas (AC-2).

## T-008 — Make the gate require the baseline; prove nightly green; backlog bookkeeping

- **Refs**: FR-7, FR-9, AC-2
- **Owner**: @agent:claude-code
- **Status**: `[ ]`
- **Files**: `Makefile`, `docs/legalbench.md`, `BACKLOG.md`
- **Steps**:
  1. Add `--require-baseline` to `test-legalbench-gate`.
  2. `gh workflow run nightly-tests.yml`; record the first green scored run id and date in `docs/legalbench.md` § "CI status of the scored gate".
  3. Move BL-20260906-28, BL-20260906-34, BL-20260811-10 and BL-20260810-04 to `## Done` with evidence (baseline commit SHA, run ids); add a note to BL-20260511-06 that its precondition is now met.
- **Verify**: `make lint-specs`; nightly step "Run LegalBench eval (regression gate)" green.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests or the recorded hosted run.
- `make lint && make typecheck && make test` green.
- LegalBench: first baseline recorded and committed (this spec's whole point); later PRs report deltas against it.
- Provenance logging verified: one sample `legalbench.item` and the `legalbench.baseline_recorded` event inspected in the audit JSONL.
- **`## Follow-ups Discovered` section below populated**.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- BL-20261018-01 — feature, med — Extend the gated LegalBench set beyond `core_reasoning`/`precedent_retrieval` to the already-fetchable `contract_nli`, `definitions` (CC BY-SA 4.0) and `causation` subsets, each with its own baseline row, once spec 056's hosted run proves the CPU budget.
- BL-20261018-02 — feature, low — A non-gating reference lane that scores the same items on `claude-sonnet-5-5` through `law_ai.core.llm` with a pinned single-tier `LLM_PROVIDER_CHAIN`; needs an ADR amending constitution §1 ("LegalBench does not route through the chain"), the `ANTHROPIC_API_KEY` secret, and a per-run cost cap (spec 056 OQ-3).
- BL-20261018-03 — test-gap, high — Four backend tests fail in the nightly "Run test coverage" step (run 38212032910: `test_tutor_reports_no_trace_when_telemetry_is_disabled`, two `test_run_autonomy_integration` cases, `test_densify_backfill_commit_writes_the_missing_cites_edge`), and the digest step logs `relation "audit_auditevent" does not exist`, so the 2026-10-05 and 2026-10-17 nightly runs failed before reaching LegalBench (the LegalBench steps were skipped).
- BL-20261018-04 — refactor, low — Report item counts and a binomial confidence interval next to every LegalBench pp delta, and decide by ADR whether the constitution §3 1 pp rule should become item-count-aware (on ~100 `precedent_retrieval` items, 1 pp is one item) (spec 056 OQ-2).
- BL-20261018-05 — infra, low — Protect `backend/var/legalbench/baseline.json`: a CODEOWNERS entry for @bamr87 and a `legalbench-baseline` label so a baseline change cannot ride along unnoticed in an unrelated PR.
- BL-20261018-06 — feature, low — Per-item flip report for LegalBench (`regressed`/`recovered` item indices between a run's `item_outcomes` and the baseline's), mirroring the LSAT `regression_report()`, surfaced in the nightly step summary.
