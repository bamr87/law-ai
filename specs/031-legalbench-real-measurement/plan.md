# Plan: Make LegalBench Measure Something Real

- **Spec**: [spec.md](spec.md) (031-legalbench-real-measurement)
- **Approach**: fix the harness so it is *ready* to measure and cannot lie
  about whether it did. Vendoring the dataset is deliberately separate
  (licensing + large-file decisions), so every change here is about making
  the machinery trustworthy rather than manufacturing a number.

## The through-line

Each defect made the same category error: **conflating "no signal" with
"a bad signal."** Reports written to an unread path, infra failure scored as
wrong answers, stub fixtures reported as accuracy, verbose-but-correct
answers scored wrong. The fix in every case is to make absence explicit.

## Steps

1. **`law_ai/eval/paths.py`** — single anchor derived from `__file__`
   (`parents[2]` = the backend dir). `loaders`, `report`, and `legalbench`
   all consume it; the CWD-relative literals are gone. Same bug class the
   TestSynthesizer fix hit in spec 026, so the same remedy.
2. **Error accounting in `run_eval`** — per-item `error` field, `errored`
   and `scored` counts per subset, accuracy over `scored` (not `n`).
   All-items-failed raises `EvalInfrastructureError`; the CLI maps it to
   exit **2** so CI can distinguish it from exit 1 (regression).
3. **Determinism** — `options: {temperature: 0, seed: 0}` on the Ollama
   call. A 1 pp policy against sampled decoding measures noise.
4. **History + baseline** — `report._append_history` writes one JSONL row
   per run; `update_baseline()` writes `baseline.json` but refuses when any
   subset is synthetic; `check_regression()` applies the §3 1 pp tolerance.
   `_load_baseline` accepts three shapes (full report, `accuracies`
   envelope, bare mapping) so old files keep working.
5. **Synthetic honesty** — `loaders.is_synthetic()`, a `synthetic` flag on
   each subset row and on the report, a `SYNTHETIC-STUBS` marker in CLI
   output, a stderr warning, and `--fail-on-synthetic` for pipelines that
   must refuse fixtures.
6. **Scoring** — add `extract_label()`: first token drawn from a closed
   label vocabulary wins, and only for closed-vocabulary expected answers.
   Chosen over "expected appears anywhere in response" precisely because
   the loose rule would score "False — it is not true that…" as correct for
   expected `True`, inflating exactly the verbose answers at issue.
7. **CI** — the PR job stops invoking the non-existent `app.` module path;
   it now runs `pytest tests/eval` (harness soundness, no model needed) and
   emits a notice pointing at nightly. Nightly switches to
   `make test-legalbench-gate` (`--check-regression`) and uploads reports +
   `history.jsonl` for 90 days.

## Test strategy

`tests/eval/test_legalbench_measurement.py` — 15 tests across four groups
mirroring the four defects: path anchoring (incl. an explicit
`backend/backend` regression assert), infra-vs-score (total failure raises;
partial failure keeps the denominator honest), baseline/history/regression
gate, and scoring (verbose-correct accepted, leading-wrong-label rejected,
free-text unaffected).

Four pre-existing tests in `test_legalbench_cli.py` patched the removed
`_CACHE_ROOT` constants and one asserted the old "score 0.0 on Ollama
error" behaviour — updated to patch the new anchors and to assert the new
`EvalInfrastructureError` contract.

Live verification (not just mocks): ran the harness in Docker against the
real Ollama — confirmed the report path resolves to `/app/var/legalbench/`
with no doubled segment, `history.jsonl` gains a row, `--fail-on-synthetic`
exits 1, and `--update-baseline` refuses stub data.

## Rollback

Revert the commit; nothing persisted is load-bearing (`baseline.json` and
`history.jsonl` are new run state). The Makefile gains two targets and
changes none of the existing ones.
