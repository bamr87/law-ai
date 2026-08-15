# Spec: Make LegalBench Measure Something Real

- **ID**: 031-legalbench-real-measurement
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (2026-08-10 audit)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §3 (LegalBench regression must not exceed 1 pp), §4 (per-item provenance), §10 (Level-3 promotion requires a tracked CI baseline)

## 1. Problem & Motivation

The project's stated goal is continuously improving accuracy, and the constitution gates PRs on "no more than 1 pp regression on listed LegalBench tasks". Neither was enforceable:

- **Reports were written where nothing reads them.** `_CACHE_ROOT` and the
default report directory were the CWD-relative literal `backend/var/legalbench`. The container runs with `CWD=/app`, which *is* the backend directory, so artifacts landed in `backend/backend/var/legalbench/` — the same bug class as the autonomy proposals fixed in spec 026.
- **Infrastructure failure was scored as wrong answers.** An unreachable
Ollama produced an empty response per item; every item scored incorrect; the run reported a cheerful `accuracy=0.0` and exited 0. That is indistinguishable from a catastrophic model regression — precisely the distinction a regression gate exists to make.
- **No baseline, no history.** No `baseline.json` was ever written and no
run was ever recorded, so "did accuracy move?" could not be answered even in principle.
- **Scoring could not support a 1 pp policy.** Exact/prefix matching scores
the ubiquitous instruction-tuned answer "The answer is True." as *wrong*, and sampling was nondeterministic run to run.
- **The CI job was dead code.** It invoked `python -m app.eval.legalbench`
  — the pre-rebrand package path — with no Ollama service and no assertion.

Verified: `backend/var/legalbench/` contained only `.gitkeep` and `LICENSES.md`, so every run to date scored 3–7 synthetic stub items.

## 2. Goals

- G1: Artifacts land where CI, the digest, and humans actually look.
- G2: "The eval could not run" is a distinct, loud outcome from "the model
  scored badly".
- G3: A tracked baseline plus append-only score history, with a real
  regression gate wired into the nightly run (BL-20260810-04).
- G4: Scoring and decoding strong enough that a 1 pp threshold is meaningful.
- G5: A run built on stub fixtures can never be mistaken for a measurement.

## 3. Non-Goals

- NG1: Fetching/vendoring the actual LegalBench dataset — that carries
licensing review and large-file decisions of its own (follow-up). This spec makes the harness *ready* for real data and refuses to pretend otherwise until it arrives.
- NG2: Per-task specialised scorers (BM25 recall, NLI entailment).
- NG3: Running a scored eval in PR-time CI — hosted runners cannot host a
multi-GB model (nightly already had to drop to weekly over disk exhaustion).

## 4. User Stories

- As a maintainer, I want a failed eval to look like a failed eval, so I
  don't chase a phantom model regression.
- As a reviewer, I want to see accuracy over time, so "continuously
  improving" is a claim I can check.
- As an agent running `/evolve`, I want a regression gate that can actually
  fail, so quality cannot silently erode.

## 5. Functional Requirements

- **FR-1**: New `law_ai.eval.paths` anchors `BACKEND_ROOT`, `CACHE_ROOT`,
`BASELINE_PATH`, `HISTORY_PATH`, and `subset_cache_path()` to the module location, never the CWD. `loaders`, `report`, and `legalbench` all use it.
- **FR-2**: An item that never reached the model is recorded with an
`error` field and **excluded from the accuracy denominator** (`scored` and `errored` counts appear per subset).
- **FR-3**: When *every* item in a subset fails, `run_eval` raises
`EvalInfrastructureError`; the CLI exits **2** (distinct from 1 = regression).
- **FR-4**: Decoding is pinned (`temperature=0`, `seed=0`) so a 1 pp
  threshold is not measuring sampling noise.
- **FR-5**: Every run appends a compact row to `history.jsonl`
  (run_id, timestamp, model, per-subset accuracy/scored/errored/synthetic).
- **FR-6**: `update_baseline()` writes per-subset accuracies to
  `baseline.json` and **refuses** when any subset used synthetic stubs.
- **FR-7**: `check_regression()` flags any subset dropping more than
  `REGRESSION_TOLERANCE_PP` (1.0) against the baseline.
- **FR-8**: CLI flags `--check-regression`, `--update-baseline`, and
`--fail-on-synthetic`; `make test-legalbench-gate` and `make legalbench-baseline` wrap them.
- **FR-9**: Reports and CLI output carry a `synthetic` flag; a stub-backed
run prints a `SYNTHETIC-STUBS` marker and a stderr warning that the numbers are not a LegalBench measurement.
- **FR-10**: Scoring adds conservative first-label extraction over a closed
vocabulary, so "The answer is True." scores correct while "False — it is not true that…" still scores incorrect. Free-text subsets keep strict matching.
- **FR-11**: The CI job stops invoking the non-existent `app.` module path;
it verifies the harness (`pytest tests/eval`) and points at nightly for the scored run. Nightly runs the gating form and uploads reports + history as a 90-day artifact.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Per-item provenance events are unchanged and still emitted.
- **NFR-DX-1**: The harness remains importable and testable without Ollama,
  Neo4j, or network access.

## 7. Data Model Impact

None. New on-disk artifacts under `backend/var/legalbench/`: `baseline.json` and `history.jsonl` (both git-ignored run state).

## 8. API Surface

CLI only. Exit codes: 0 clean · 1 regression / refused baseline / `--fail-on-synthetic` · 2 infrastructure failure.

## 9. Agent / Crew Impact

None — the harness calls Ollama directly and does not route through agents.

## 10. Acceptance Criteria

- **AC-1**: `CACHE_ROOT` is absolute, sits under the backend package, and
  contains no `backend/backend` segment; the default report path is inside it.
- **AC-2**: Total Ollama failure raises `EvalInfrastructureError` rather
  than reporting accuracy 0.0.
- **AC-3**: Partial failure excludes errored items from the denominator
  (1 correct of 1 scored ⇒ 1.0, not 0.5) and records the error per item.
- **AC-4**: Two runs append two rows to `history.jsonl` with per-subset
  accuracies and the synthetic flag.
- **AC-5**: `update_baseline` refuses a synthetic run.
- **AC-6**: `check_regression` flags a 5 pp drop and ignores a 0.5 pp drop;
  improvements are never regressions.
- **AC-7**: "The answer is True." / "Answer: yes" score correct;
  "False — it is not true that…" and "" score incorrect.
- **AC-8**: Label extraction returns `None` for free-text responses, so
  non-label subsets keep strict matching.

## 11. LegalBench Impact

- Tasks affected: all listed subsets — but the *measurement* changes, not
the model. Accuracy numbers from before this spec are not comparable: they were computed over stub fixtures, with infra failures counted as wrong answers, under nondeterministic sampling.
- Expected delta: not applicable until a real dataset is cached; the first
  real run establishes the baseline.

## 12. Risks & Open Questions

- **R-1**: Until a real dataset is cached, `--check-regression` has nothing
to compare and exits 0 with a note. The `--fail-on-synthetic` flag exists for pipelines that must refuse to proceed on fixtures.
- **R-2**: First-label extraction is a heuristic. It is deliberately
conservative (first label wins, closed vocabulary only), but a task whose correct answer legitimately begins by naming the opposite label would be mis-scored. No such subset is currently listed.
- **R-3**: Pinning `seed=0` makes runs reproducible per model build but does
not make different Ollama/model versions comparable — hence the pinned image tag from spec 026.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as BL-20260811-09 … BL-20260811-12).
