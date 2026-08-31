# Tasks: Interactive LSAT solving aids — progressive hints + incremental diagrams

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Guide domain models + loader

- **Refs**: FR-1, FR-2, NFR-PERF-1, AC-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/guides.py` (new)
  - `backend/tests/lsat/test_guides.py` (new)
- **Steps**:
  1. Define `SolveStep{kind, title, text, representation?, spoiler}` with `kind ∈ {orient, inventory, symbolize, diagram, infer, eliminate, answer}`; validator forces `spoiler=True` on `answer`-kind steps.
  2. Define the `rep_type`-discriminated union: `SequenceRep`, `GridRep`, `NotationRep`, `ArgumentMapRep`, `PassageMapRep`; unknown `rep_type` rejected by Pydantic.
  3. Define `SolveGuide{question_id, method, steps (min 1), version, source}` and `load_guides()` (`@lru_cache`, reads `data/guides.json`, validates every `question_id` against `load_bank()`, fails loudly otherwise), `public_guide_view(guide, include_spoilers)` returning locked stubs for withheld steps, `reset_guide_cache()` (also wired into `bank.reset_caches()` pattern via its own function tests call).
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_guides.py -q` passes (unknown-id, empty-steps, unknown-rep_type rejections + spoiler stripping covered).
  - `make typecheck` clean on touched files.

## T-002 — Seed guide content (hand-authored)

- **Refs**: FR-3, NFR-HITL-1, AC-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/guides.json` (new)
- **Steps**:
  1. Author ≥ 9 guides against existing bank questions: ≥ 3 LG (using `sequence`, `grid`, `notation` reps), ≥ 3 LR (`argument_map`, `notation`), ≥ 3 RC (`passage_map`); every guide ≥ 4 steps ending in a spoiler `answer` step; `source: "original (CC0)"`.
  2. Horizontal orientation semantics for `sequence` slots (resolved OQ-3).
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_guides.py -q` — seed-file load test passes (all ids resolve, coverage counts asserted).

## T-003 — Guide endpoint + hint-aware grading & stats

- **Refs**: FR-4, FR-5, NFR-SEC-1, NFR-AUDIT-1, NFR-TEST-1, AC-2, AC-3
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/urls.py`
  - `backend/tests/api/test_lsat_guides.py` (new)
- **Steps**:
  1. `GuideView` (GET `questions/<question_id>/guide`): default spoiler-stripped via `public_guide_view`; `?spoilers=1` returns full steps; 404 `{detail, has_tutor: true}` for unknown question or guide-less question; emits `lsat_guide` audit event (try/except-log like `GradeView`).
  2. `GradeRequest` gains `hints_used: int | None = Field(default=None, ge=0, le=20)`; recorded in the `lsat_grade` event.
  3. `StatsView` adds `assisted`/`unassisted` counts (attempt with `hints_used > 0` is assisted) overall and per section bucket.
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_lsat_guides.py tests/api/test_lsat.py -q` passes.
  - `make typecheck` clean.

## T-004 — Proposals store: guide kind + promotion

- **Refs**: FR-9, NFR-HITL-1, AC-6
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/proposals.py`
  - `backend/tests/lsat/test_proposals.py`
- **Steps**:
  1. `record_proposal(..., proposal_kind: str = "question")` stored on the create event; `_replay` backfills `"question"` for legacy rows.
  2. `promote_to_bank` raises `ValueError` for `proposal_kind == "guide"`; new `promote_guide_to_bank(proposal_id, reviewer, note)` validates the draft as `SolveGuide`, appends to `guides.json`, clears the guide cache, sets status approved, mirrors `lsat_proposal.approved` audit event.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_proposals.py -q` passes (guide promotion, kind guard, legacy replay).

## T-005 — LSATSolveGuideAuthor crew + prompt + generate endpoint

- **Refs**: FR-9, NFR-AUDIT-1, NFR-HITL-1, NFR-SEC-1, AC-6
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/crews/lsat_solve_guide_author.py` (new)
  - `backend/law_ai/agents_runtime/prompts/lsat_solve_guide_author.v1.md` (new)
  - `backend/law_ai/agents_runtime/registry.py`
  - `backend/law_ai/lsat/urls.py` (`GuideGenerateView`, throttle scope `llm`)
  - `backend/tests/agents/test_lsat_solve_guide_author.py` (new)
  - `docs/agent-roles.md`
- **Steps**:
  1. Crew mirrors `lsat_content_author.py`: `GenerateGuideInput{question_id}`, versioned prompt, `llm.agenerate(..., agent="lsat_guide_author")` with a structured-output schema, parse → `SolveGuide` validation, deterministic offline fallback (`confidence=0.0`, degraded), one `provenance.log_agent_call` parent event, `human_approval_required = True`.
  2. `POST /api/lsat/guides/generate {question_id}` runs the crew and persists the draft via `record_proposal(..., proposal_kind="guide")`; single-question only (resolved OQ-2).
  3. Register in `registry.py`; add the role to `docs/agent-roles.md` (NFR-DOCS-1).
- **Verify**:
  - `docker compose run --rm backend pytest tests/agents/test_lsat_solve_guide_author.py tests/api/test_lsat_guides.py -q` passes (draft never visible on GET guide until approved).
  - `make typecheck` clean.

## T-006 — Frontend API client + shared MSW handlers

- **Refs**: FR-10, NFR-TEST-1, AC-2
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts`
  - `frontend/mocks/server.ts`
  - `frontend/__tests__/lib/api.lsatGuide.test.ts` (new)
- **Steps**:
  1. Mirror FR-2 types (`LsatSolveGuide`, `LsatSolveStep`, `LsatRepresentation` union); `fetchLsatGuide(questionId, opts?: {spoilers?: boolean})` returning `{guide}` or throwing a typed `LsatGuideNotFound` carrying `has_tutor`; `gradeLsat` gains optional `hintsUsed` mapped to `hints_used`.
  2. Add shared LSAT guide MSW handlers + fixtures to `mocks/server.ts`.
- **Verify**:
  - `make test-frontend` green including the new client test.

## T-007 — Diagram renderers (parallel)

- **Refs**: FR-7, NFR-A11Y-1, NFR-PERF-1, AC-5
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/components/lsat/diagrams/{Representation,SequenceBoard,GroupGrid,RuleNotation,ArgumentMap,PassageMap}.tsx` (new)
  - `frontend/__tests__/components/lsat/diagrams.test.tsx` (new)
- **Steps**:
  1. `Representation` dispatcher — exhaustive switch on `rep_type` (compile-time `never` check).
  2. `SequenceBoard`: horizontal SVG slots + entity chips, fixed/excluded marks (symbol + colour, never colour alone); `role="img"` + generated `aria-label`.
  3. `GroupGrid`: semantic `<table>` with caption; `RuleNotation`: monospace symbol strings + text legend (`→`, `¬`, `—`); `ArgumentMap`: SVG premise/conclusion boxes + arrows; `PassageMap`: ordered list of paragraph roles.
  4. All render inside `overflow-x-auto` containers, legible at 320 px, dark-theme tokens, no new deps.
- **Verify**:
  - `make test-frontend` green — one render + one a11y assertion per renderer.

## T-008 — SolveAssist progressive reveal + Lab wiring

- **Refs**: FR-6, FR-8, NFR-A11Y-1, NFR-TEST-1, AC-4, AC-7
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/components/lsat/SolveAssist.tsx` (new)
  - `frontend/components/LsatLab.tsx` (mount points only)
  - `frontend/__tests__/components/lsat/SolveAssist.test.tsx` (new)
- **Steps**:
  1. `SolveAssist({questionId, graded, onHintsUsedChange})`: lazy-fetch guide on first "Hint" click; reveal one step per click into an `aria-live="polite"` region; spoiler steps render locked stubs until `graded`, then "Show final step" refetches with `spoilers=1`; 404 branch renders the tutor CTA (FR-8 canned walkthrough question wired to the existing `TutorPane` entry point).
  2. `LsatLab.tsx`: `QuestionCard` mounts `SolveAssist` and threads `hintsUsed` into `gradeLsat`; header session score shows `· N assisted` (resolved OQ-1).
  3. Full gates: `make lint`, `make typecheck`, `make test` (AC-7).
- **Verify**:
  - `make test-frontend` green — reveal-one-per-click, locked-until-graded, unlock-after-grade, tutor-fallback cases.
  - `make lint && make typecheck && make test` green; `python3 scripts/spec_validator.py specs/041-lsat-solving-aids` exits 0.

## T-009 — Guide quality validator wired into all three choke points

- **Refs**: FR-11, NFR-HITL-1, NFR-TEST-1, AC-8
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/guides.py` (`validate_guide_quality`)
  - `backend/law_ai/lsat/services/proposals.py` (`promote_guide_to_bank` gate)
  - `backend/law_ai/agents_runtime/crews/lsat_solve_guide_author.py` (`_parse_guide` gate)
  - `backend/law_ai/lsat/services/data/guides.json` (complete-elimination steps re-flagged spoiler)
  - `backend/tests/lsat/test_guides.py`, `backend/tests/agents/test_lsat_solve_guide_author.py`
- **Steps**:
  1. `validate_guide_quality(guide, question)` — answer-leak patterns, complete-elimination detection, answer-step grounding, sequence/grid internal consistency; returns problem strings.
  2. Wire into `load_guides()` (seed gate, fails CI not user requests), `_parse_guide` (LLM draft → degraded fallback on failure), and `promote_guide_to_bank` (raises before write).
  3. Re-flag the seed guides' full-elimination steps as spoilers so shipped content passes its own gate.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_guides.py tests/agents/test_lsat_solve_guide_author.py -q` passes (leak, elimination, board-consistency, answer-grounding rejections + clean seed pass).

## T-010 — Remove author rationale + external links from the answer component

- **Refs**: FR-12, NFR-TEST-1, AC-9
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/components/LsatLab.tsx` (rationale block removed from `QuestionCard`)
  - `frontend/components/lsat/ConceptRefs.tsx` (new)
  - `frontend/mocks/server.ts` (shared `/api/lsat/concepts` handler + fixture)
  - `frontend/__tests__/components/lsat/ConceptRefs.test.tsx` (new)
  - `frontend/__tests__/components/LsatLab.test.tsx` (grade-test assertions)
- **Steps**:
  1. Delete the post-grade "Author rationale" block (explanation text + `question.references` external `<a href>` links) from `QuestionCard`.
  2. Replace with `ConceptRefs`: resolves the union of grade-response and question concept ids against the in-app catalog, rendering name, summary, and schema examples — never any anchor; unresolvable ids fall back to plain chips.
  3. Update the Lab grade test to assert the rationale and external links are gone and the concept references render.
- **Verify**:
  - `make test-frontend` green — ConceptRefs renders concepts without links; Lab grade flow shows "Derived from" and no `Author rationale` / external anchors.

## T-011 — Full LG seed coverage + batch guide backfill command

- **Refs**: FR-3, FR-9, NFR-HITL-1, NFR-TEST-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/guides.json` (40 guides: all 19 LG, 16 LR, 5 RC)
  - `backend/law_ai/lsat/management/commands/lsat_guide_backfill.py` (new)
  - `backend/tests/lsat/test_guide_backfill.py` (new)
- **Steps**:
  1. Hand-author guides for every remaining LG question (all four games: sequencing locals/globals, parity deduction, grouping contrapositive chains) plus the LR conditional/flaw/assumption core and passage-001 RC set — all clearing the FR-11 quality gate.
  2. `lsat_guide_backfill` command (resolves BL-20260830-11): iterates guide-less questions minus pending guide proposals, runs `LSATSolveGuideAuthor` per question, records `proposal_kind="guide"` pending rows; `--section`, `--limit` budget cap (default 5), `--dry-run`, `--include-degraded` (degraded drafts skipped by default).
  3. Command tests: dry-run listing, queueing, pending-dedup across runs, degraded skip/include, bad-section rejection.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_guides.py tests/lsat/test_guide_backfill.py -q` passes (all 40 guides clear the quality validator).

## T-012 — SolveAssist carousel presentation

- **Refs**: FR-6, NFR-A11Y-1, AC-4
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/components/lsat/SolveAssist.tsx`
  - `frontend/__tests__/components/lsat/SolveAssist.test.tsx`
- **Steps**:
  1. Replace the stacked step list with a carousel: one slide at a time (`role="region"` + `aria-roledescription="carousel"`, slides as `role="group"`/`aria-roledescription="slide"`, `aria-live` swap region), ‹ Back / Next › navigation, clickable step dots (`aria-current="step"`; unrevealed steps as dimmed placeholders showing total length).
  2. Reveal semantics unchanged: the Next button reads "💡 Next hint ›" only at the frontier when it will reveal a new step (one per click, AC-4); within revealed steps it navigates; spoiler locking, "Show final step", session depth persistence, and `hints_used` counting are untouched.
  3. Tests rewritten for carousel behavior: single-slide invariant, back/forward/dot navigation, frontier reveal labelling, locked-stub + unlock flow, hints-used counting, tutor fallback.
- **Verify**:
  - `make test-frontend` green (6 SolveAssist carousel cases; full suite passes).

## T-013 — Walkthrough cache + answer cross-check + question-set review

- **Refs**: FR-13, FR-14, FR-15, NFR-AUDIT-1, NFR-SEC-1, NFR-TEST-1, AC-10, AC-11, AC-12
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/llm_cache.py` (new — keyed JSONL response store)
  - `backend/law_ai/lsat/services/tutor.py` (cache lookup/write, `refresh`, `cached`)
  - `backend/law_ai/lsat/services/crosscheck.py` (new — blind solve vs. answer key)
  - `backend/law_ai/lsat/services/validation.py` (new — deterministic set review)
  - `backend/law_ai/lsat/urls.py` (`CrossCheckView`, `ValidationView`)
  - `backend/tests/api/test_lsat_crosscheck.py` (new), `backend/tests/api/test_lsat.py` (cache isolation)
  - `frontend/lib/api.ts`, `frontend/mocks/server.ts`
  - `frontend/components/lsat/{CrossCheckPanel,ValidationReport}.tsx` (new)
  - `frontend/components/LsatLab.tsx` (mounts + tutor cached badge/regenerate)
  - `frontend/__tests__/components/lsat/{CrossCheckPanel,ValidationReport}.test.tsx` (new)
- **Steps**:
  1. FR-13: cache LLM tutor walkthroughs keyed on (question, choice, follow-up, prompt version); identical repeats serve the stored copy (`cached: true`, no model call); offline fallbacks never cached; `refresh` bypasses; audit events carry `cached`.
  2. FR-14: `POST /api/lsat/questions/<id>/cross-check` (throttle `llm`) solves the question blind — the prompt never contains the answer key — and compares the pick to the key; disagreement sets `requires_human_review`; verdicts cached; UI panel reports agreement as corroboration by a named model, never as proof (§13).
  3. FR-15: `GET /api/lsat/validation` deterministic report — per-question integrity issues, answer-key distribution (counts, not judgments), stored cross-check roll-up with disagreements listed — rendered on the Authoring tab.
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_lsat_crosscheck.py tests/api/test_lsat.py -q` passes (cache hit/miss/refresh, offline honesty, agree/disagree/audit, report shape).
  - `make test-frontend` green (CrossCheckPanel + ValidationReport cases).

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make typecheck && make test` green.
- LegalBench delta: n/a (spec §11 — no reasoning-logic change).
- Provenance logging verified for the new agent path (`llm_call` + `log_agent_call` events observed in the audit log during T-005 verification).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- **BL-20260830-11** — feature, med — Guide coverage is 9/126 bank questions. Add budget-capped batch drafting (the OQ-2 deferral) so `LSATSolveGuideAuthor` can fill guide-less questions section by section through the existing HITL queue.
- **BL-20260830-12** — feature, low — Port `SolveAssist` + the diagram renderers into `lsat-static` so the serverless drill gets the same hint system (natural companion to the BL-20260830-04 timer unification).
- **BL-20260830-13** — feature, low — Per-reveal hint audit events (`lsat_hint`): today only grade-time `hints_used` is recorded, so analytics cannot distinguish a 1-hint from a 5-hint assist or hints on questions never submitted.
- **BL-20260830-14** — test-gap, low — The guide-proposal review card in `AuthoringPanel` (added because question-shaped `ProposalCard` crashed on guide drafts) has no dedicated Vitest coverage; the approve→serve path is tested only at the API layer.
- **BL-20260831-01** — feature, med — Batch cross-check sweep: a budget-capped management command (mirroring `lsat_guide_backfill`) that runs the FR-14 blind solve across guide-less/unchecked questions section by section, so the validation report's cross-check coverage can grow without manual per-question clicks; disagreements should additionally land as reviewable rows in the HITL queue, not just in the report.
- **BL-20260830-15** — feature, med — LLM judge tier for guide drafts: `validate_guide_quality` (FR-11) is deterministic lint; a `LSATGuideReviewer` agent should additionally judge pedagogical soundness (does each step follow? is the symbolization faithful?) before a human sees the draft — companion to the question-side judge tier (BL-20260702-02) and reviewer crew (BL-20260527-04).
