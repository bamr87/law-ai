# Tasks: Make LegalBench Measure Something Real

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Anchor every eval path (FR-1, AC-1, NFR-DX-1)
  - New `law_ai/eval/paths.py` (`BACKEND_ROOT`, `CACHE_ROOT`, `BASELINE_PATH`, `HISTORY_PATH`, `subset_cache_path`) derived from the module location; `loaders`, `report`, and `legalbench` consume it. Verified live: reports now land at `/app/var/legalbench/`, not `/app/backend/var/legalbench/`.
- [x] **T-002** — Infrastructure failure is not a score (FR-2, FR-3, AC-2, AC-3)
  - Per-item `error`, per-subset `scored`/`errored`, accuracy over items that actually ran; total failure raises `EvalInfrastructureError` and the CLI exits 2 (vs 1 for a regression).
- [x] **T-003** — Deterministic decoding (FR-4)
  - `temperature=0`, `seed=0` on every generate call, so a 1 pp threshold is not measuring sampling noise.
- [x] **T-004** — Baseline, history, and a regression gate that can fail (FR-5, FR-6, FR-7, FR-8, AC-4, AC-5, AC-6)
  - `history.jsonl` appended per run; `update_baseline()` (refuses stub data); `check_regression()` at the §3 1 pp tolerance; CLI flags `--check-regression` / `--update-baseline` / `--fail-on-synthetic`; `make test-legalbench-gate` and `make legalbench-baseline`.
- [x] **T-005** — Synthetic runs can never pose as measurements (FR-9)
  - `is_synthetic()`, `synthetic` flags on subset rows and the report, a `SYNTHETIC-STUBS` marker in CLI output, a stderr warning, and a sharpened loader warning. Verified live: `--fail-on-synthetic` exits 1 and `--update-baseline` refuses.
- [x] **T-006** — Scoring strong enough for the policy (FR-10, AC-7, AC-8)
  - Conservative first-label extraction over a closed vocabulary: "The answer is True." scores correct; "False — it is not true that…" still scores incorrect; free-text subsets keep strict matching.
- [x] **T-007** — CI wiring (FR-11, NFR-AUDIT-1)
  - PR job stops invoking the pre-rebrand `app.eval.legalbench` path and verifies the harness with `pytest tests/eval`; nightly runs the gating form and uploads reports + `history.jsonl` (90-day retention).
- [x] **T-008** — Tests (AC-1 … AC-8)
  - 15 new tests in `tests/eval/test_legalbench_measurement.py`; 4 pre-existing tests updated for the new path anchors and the infrastructure-error contract. Full backend suite green (78.49%).

## Follow-ups Discovered

- Fetch and cache the real LegalBench dataset (the whole point of the
harness): a `scripts/fetch_legalbench.py` with per-task licence review, a pinned revision, and a decision on vendoring vs downloading in CI. Until this lands every run is stub-backed and `--check-regression` has nothing to compare.
- Establish and commit the first real baseline once the dataset is cached,
then flip nightly to `--fail-on-synthetic` so a stub-backed run can never satisfy the gate.
- Per-task scorers (BM25 recall for retrieval subsets, entailment for
`contract_nli`) — the current task-agnostic matcher is a floor, not a ceiling.
- Publish the score history somewhere reviewers see it (digest section or a small chart in the agent-ops dashboard); today it is only a CI artifact.
