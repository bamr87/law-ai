# Tasks: LSAT Continuous Curriculum

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.
- Tasks are grouped into **slices**; one slice = one PR. Slices ship in order — slice 5 (export profiles) deliberately precedes slice 6 (publishing more machine-derived content) so the bundle-size mitigation exists before the growth.

---

# Slice 1 — Writing sample vertical

## T-001 — Writing content model + loaders

- **Refs**: FR-1, AC-1, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/writing.py` (new)
  - `backend/law_ai/lsat/services/bank.py` (edit — `Section` gains `"WS"`, `Question` rejects it)
- **Steps**:
  1. Model `WritingRubric` (weighted criteria × ordered performance bands) and `WritingPrompt` (scenario, two decision positions, perspectives, task, model response, self-check).
  2. Add lazy `lru_cache` loaders mirroring `bank.py`, with cross-reference validation: unknown rubric id, unknown criterion id in a self-check or annotation, or a duplicate prompt id fails the load.
  3. Add a `public_prompt_view` that withholds the model response unless explicitly asked.
  4. Widen `Section` to include `"WS"` and add a `Question` validator rejecting it.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_writing.py -q --no-cov` passes.
  - `make typecheck` clean.

## T-002 — Seed the writing prompt library and rubric

- **Refs**: FR-2, AC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/writing_rubrics.json` (new)
  - `backend/law_ai/lsat/services/data/writing_prompts.json` (new)
  - `backend/law_ai/lsat/services/data/sections.json` (edit — add the WS section entry)
  - `backend/law_ai/lsat/services/data/concepts.json` (edit — argumentative-writing concepts)
- **Steps**:
  1. Author one rubric with weighted criteria and ordered bands covering argument construction, use of the given criteria, treatment of the opposing position, evidence and reasoning, and written expression.
  2. Author prompts spanning the recurring decision shapes, each with two positions, perspectives, an annotated model response, and a self-check list keyed to rubric criteria.
  3. Add the `WS` `SectionInfo` entry with format, timing, scoring and tips; tag the new writing concepts.
- **Verify**: loaders accept the files; `docker compose run --rm backend pytest tests/lsat/test_writing.py -q --no-cov` passes.

## T-003 — `LSATWritingEvaluator` agent

- **Refs**: FR-4, NFR-AUDIT-1, NFR-PROV-1, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/crews/lsat_writing_evaluator.py` (new)
  - `backend/law_ai/agents_runtime/prompts/lsat_writing_evaluator.v1.md` (new)
  - `backend/tests/agents/test_lsat_writing_evaluator.py` (new)
- **Steps**:
  1. Implement `run(input: dict) -> WritingEvaluationOutput` following `LSATSolveGuideAuthor`: `llm.agenerate` only, one `provenance.log_agent_call` per run, `human_approval_required = True`.
  2. Parse a per-criterion band + evidence quote + improvement note; reject a response that omits a criterion.
  3. Deterministic degraded fallback at confidence 0.0 when every provider fails.
- **Verify**: `docker compose run --rm backend pytest tests/agents/test_lsat_writing_evaluator.py -q --no-cov` passes.

## T-004 — Writing API routes

- **Refs**: FR-5, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/urls.py` (edit)
  - `backend/tests/api/test_lsat_writing.py` (new)
- **Steps**:
  1. Add `GET writing/prompts`, `GET writing/prompts/<id>`, `GET writing/rubric`, `POST writing/evaluate` (`ScopedRateThrottle`, `llm` scope).
  2. Withhold model responses on the list endpoint and on detail unless `?model_response=1`.
  3. Record an `lsat_writing_evaluate` audit event.
  4. Add `writing_prompt_count` to the sections payload.
- **Verify**: `docker compose run --rm backend pytest tests/api/test_lsat_writing.py -q --no-cov` passes.

## T-005 — Export writing content into the static artifact

- **Refs**: FR-6, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/management/commands/lsat_export.py` (edit)
  - `backend/tests/lsat/test_export_site.py` (edit)
  - `lsat-static/content.json` (regenerated)
- **Steps**:
  1. Add `writing_prompts` and `writing_rubrics` to `build_content()` under stable id ordering; extend `counts`.
  2. Bump `SCHEMA_VERSION`.
  3. Run `make lsat-export`.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_export_site.py -q --no-cov` passes; `content.json` re-export is byte-stable apart from `generated_at`.

## T-006 — Static-site Writing view

- **Refs**: FR-3, NFR-OFFLINE-1, AC-6
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `lsat-static/lib/types.ts` (edit), `lsat-static/lib/data.ts` (edit)
  - `lsat-static/components/Writing.tsx` (new)
  - `lsat-static/app/page.tsx` (edit — nav entry), `lsat-static/app/globals.css` (edit)
- **Steps**:
  1. Type the writing payload and add accessors.
  2. Build the view: prompt picker → 35-minute timed drafting surface with `localStorage` persistence → rubric self-score → annotated model response revealed only after submitting.
  3. Make zero network calls; keep the single-`contentinfo` landmark rule intact.
- **Verify**: `cd lsat-static && npm run build` succeeds; the drift gate and structure tests in `tests/test_lsat_site.py` pass.

## T-007 — Root-suite coverage for writing content

- **Refs**: AC-5, AC-6, NFR-OFFLINE-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `tests/test_lsat_site.py` (edit)
- **Steps**: assert the artifact carries writing prompts and rubrics, that they match the source data files field-for-field, and that the Writing component file exists.
- **Verify**: `python3 -m pytest tests/test_lsat_site.py -q` (stdlib-only root suite) passes.

## T-008 — Slice 1 gates and docs

- **Refs**: NFR-AUDIT-1, NFR-HITL-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `docs/agent-roles.md` (edit), `specs/047-lsat-continuous-curriculum/tasks.md` (this file)
- **Steps**: register `LSATWritingEvaluator` in the agent-roles doc with its HITL posture; run every gate.
- **Verify**: `make lint`, `make typecheck`, `make test`, `make lint-specs` all green.

---

# Slice 2 — Question-type and difficulty expansion

## T-010 — Archetype expansion

- **Refs**: FR-7, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/factory/taxonomy.py`, `backend/law_ai/lsat/services/data/concepts.json`, `backend/tests/lsat/test_factory_taxonomy.py`
- **Steps**: add the LR, RC and LG archetypes named in FR-7 with item-writing guidance and exam-frequency weights; add the concepts they need.
- **Verify**: `validate_taxonomy()` passes; taxonomy tests cover every new id.

## T-011 — Difficulty band expansion

- **Refs**: FR-8
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/services/bank.py`, `backend/law_ai/lsat/factory/{config,coverage}.py`, `lsat-static/lib/types.ts`
- **Steps**: widen the `Difficulty` literal with a documented mapping from `easy|med|hard`; keep every stored item valid; update tier routing.
- **Verify**: full backend suite green with no data-file edits required.

## T-012 — Comparative RC passages

- **Refs**: FR-9
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/services/bank.py`, `data/passages.json`, `data/rc_bank.json`, `lsat-static/components/PassagePanel.tsx`, `frontend/components/LsatLab.tsx`
- **Steps**: model a comparative set (Passage A / Passage B), author one, render both halves side by side in both apps.
- **Verify**: API and export carry both halves; both UIs render them.

---

# Slice 3 — Diagramming methods

## T-020 — New typed representations

- **Refs**: FR-10, AC-8
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/services/guides.py`, `backend/tests/lsat/test_guides.py`
- **Steps**: add conditional-chain, causal-map, quantifier-overlap, in/out board, numeric-distribution, branch-tree, elimination-trace and comparative-map representations to the discriminated union, each with its own consistency lint alongside `_lint_sequence_rep` / `_lint_grid_rep`.
- **Verify**: guide loader rejects an internally inconsistent instance of each new type.

## T-021 — Renderers in both apps

- **Refs**: FR-11, AC-8
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `frontend/components/lsat/diagrams/*`, `lsat-static/components/solve/diagrams/*`, `frontend/__tests__/components/lsat/diagrams.test.tsx`
- **Steps**: one renderer per new representation, dispatched from the shared `Representation` component in both apps; author one guide per type exercising it.
- **Verify**: `make test-frontend` green; every representation type has a bank guide using it.

---

# Slice 4 — Concept depth and linking

## T-030 — Enrich every concept

- **Refs**: FR-12, AC-9
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/services/data/concepts.json`, `backend/law_ai/lsat/services/bank.py`, `backend/tests/lsat/test_concepts.py` (new)
- **Steps**: add a detail body, two worked examples, a reference and a common-trap list to all 30 concepts; add a test that fails on any concept missing one.
- **Verify**: the new test passes and fails when a field is removed.

## T-031 — Concept graph and per-concept page

- **Refs**: FR-13, FR-14
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/services/bank.py`, `backend/law_ai/lsat/urls.py`, `lsat-static/components/Concepts.tsx`, `frontend/components/lsat/ConceptRefs.tsx`
- **Steps**: compute bidirectional concept↔question / archetype / guide / section links and a prerequisite ordering; expose them on the concept detail endpoint and in the export; build the per-concept page with a "drill this concept" action.
- **Verify**: every link resolves in both directions; the drill action filters the bank.

---

# Slice 5 — Offline and abbreviated copies

## T-040 — Export profiles and sharding

- **Refs**: FR-15, NFR-PERF-1, AC-10
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/management/commands/lsat_export.py`, `Makefile`, `backend/tests/lsat/test_export_site.py`
- **Steps**: add `--profile full|lite|section:<CODE>` and optional per-question guide shards; add `make lsat-export-lite`.
- **Verify**: the lite profile is materially smaller; both profiles are byte-stable across runs.

## T-041 — Printable study packets

- **Refs**: FR-16, NFR-OFFLINE-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/management/commands/lsat_packet.py` (new), `Makefile`, `backend/tests/lsat/test_packet.py` (new)
- **Steps**: emit Markdown problem sets with answer keys and guide walkthroughs, selectable by section / concept / difficulty, generated in Docker via `make lsat-packet`.
- **Verify**: byte-identical output for unchanged content; no network calls.

---

# Slice 6 — Publishing machine-derived explanation

## T-050 — Guide backfill to full coverage

- **Refs**: FR-18, AC-11
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/management/commands/lsat_guide_backfill.py`, `backend/law_ai/lsat/services/data/guides.json`
- **Steps**: run the backfill through the HITL queue until every bank question has a guide (BL-20260831-23).
- **Verify**: a test asserts guide coverage is total.

## T-051 — Publish rationales and cross-check verdicts

- **Refs**: FR-17, NFR-PROV-1, AC-11
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/services/{crosscheck,bank}.py`, `lsat_export.py`, `lsat-static/components/QuestionCard.tsx`
- **Steps**: add per-choice rationales and stored cross-check verdicts to the export, each labelled with model and prompt version; render the label wherever the content shows.
- **Verify**: no machine-derived string renders without its provenance label.

---

# Slice 7 — The continuous loop

## T-060 — Revision path in the factory

- **Refs**: FR-19
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/factory/{coverage,pipeline}.py`, `backend/law_ai/agents_runtime/crews/lsat_content_author.py`
- **Steps**: plan *revision* targets from cross-check disagreements, validation findings and weak learner accuracy; draft a revision of the existing item rather than a new one.
- **Verify**: a seeded disagreement produces a revision target and a revision proposal.

## T-061 — `LSATDraftJudge` and the auto-promotion gate

- **Refs**: FR-20, NFR-HITL-1, AC-12
- **Owner**: @bamr87
- **Status**: `[ ]`
- **Files**: `backend/law_ai/agents_runtime/crews/lsat_draft_judge.py` (new), `backend/law_ai/lsat/services/proposals.py`, `backend/law_ai/lsat/factory/intake.py`
- **Steps**: wire the `judge` tier `FactoryConfig` already defines (BL-20260702-02); require deterministic validation **and** judge pass **and** blind cross-check agreement before auto-promotion; store all three verdicts on the proposal row; add the kill flag, default off.
- **Verify**: failing any one gate blocks promotion; the flag off routes everything to HITL.

## T-062 — Scheduled cycle

- **Refs**: FR-21, NFR-COST-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/tasks.py` (new), `backend/law_ai/settings/base.py`, `Makefile`, `.github/workflows/` (optional dispatch)
- **Steps**: Celery beat entry running plan → compile → generate → judge → cross-check → promote-or-queue through `autonomy.run_cycle`, budget-capped, gated by `AUTONOMY_ENABLED`.
- **Verify**: a cycle exceeding its budget ends and records the reason; disabled autonomy emits `autonomy_disabled` and does nothing.

## T-063 — Curriculum health report

- **Refs**: FR-22, AC-12
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: `backend/law_ai/lsat/services/health.py` (new), `backend/law_ai/lsat/urls.py`, `backend/tests/lsat/test_health.py` (new)
- **Steps**: compute coverage deficit, guide coverage, concept enrichment, key balance, cross-check agreement rate and bank size by section/difficulty; emit per cycle and expose at `GET /api/lsat/curriculum/health`.
- **Verify**: the report is deterministic for a fixed bank and each metric moves when its input changes.

---

## T-013 — Compact, responsive navigation and motion

- **Refs**: FR-3, NFR-OFFLINE-1, NFR-PERF-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `lsat-static/app/page.tsx`, `lsat-static/app/globals.css`
  - `lsat-static/components/{Overview,PassagePanel}.tsx`
- **Steps**:
  1. Compact the nav: seven full-length destinations wrapped a second row at *every* width once Writing was added, pushing the header to 101px on desktop and 136px on a phone and desynchronising the `--site-header-h` offset the sticky drill head and passage column hang from. Section codes carry the sections; `aria-label` and `title` keep the full names.
  2. Make the row scroll rather than wrap, pull the active destination into view on change, and fade the trailing edge only while it overflows (ResizeObserver, so rotation does not leave a stale answer).
  3. Add an entrance animation per destination — fade above 820px where the passage column is sticky (an animated `transform` would create a containing block and break sticky), fade-and-rise below.
  4. Raise every control to the 44px touch guideline at phone widths and on coarse pointers; honour `prefers-reduced-motion` for all of it.
- **Verify**:
  - At 390px: header 136px → 85px, no control under 44px, no horizontal overflow, nav scrolls with the active pill in view.
  - At 1280px: header 61px against the 60px `--site-header-h` token, one nav row, passage column still `position: sticky`.
  - `make ux-audit` and `make lsat-static-build` both clean.

---

## T-014 — Scroll-directional header on narrow viewports

- **Refs**: FR-3, NFR-PERF-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `lsat-static/app/page.tsx`, `lsat-static/app/globals.css`
- **Steps**:
  1. Three header states on a scroll listener — `top` (brand row + nav strip), `condensed` (brand row collapses once the page moves), `hidden` (the bar slides away past a screenful). Scrolling up returns to `condensed` at any depth, so the nav is one upward flick away rather than a scroll home.
  2. Direction-keyed with a 6px dead zone (momentum and rubber-banding both jitter) and rAF-throttled on a passive listener.
  3. Animate `transform`, never `top` or `height`: a transform does not reflow, so content underneath never shifts, and no sticky offset is hand-written (`ux_audit.py` R9).
  4. Scope the CSS to `max-width: 819px`. Above that the drill head and passage column are sticky at offsets keyed off `--site-header-h`, and a moving header would desynchronise both.
  5. Escape hatches: any focus landing inside a hidden header restores it (a browser will not reliably scroll a transformed sticky element into view), and a destination change resets scroll and returns the header.
- **Verify** (measured in a real browser at 390x844 and 1280x900):
  - 390px: 85px at rest → 60px condensed at 60px of scroll → off-screen (`top: -61`) past 220px → back to 60px condensed on an upward flick → 85px at the top.
  - Focus on a nav button while hidden restores the bar to `top: 0`.
  - 1280px: class still changes, but `transform: none`, `top: 0`, height 61px — the wide layout is untouched.
  - `make ux-audit` and `make lsat-static-build` clean.

---

## T-015 — Full keyboard progression through every exam section

- **Refs**: FR-3, NFR-OFFLINE-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `lsat-static/lib/keyboard.ts` (new), `lsat-static/components/ShortcutHelp.tsx` (new)
  - `lsat-static/app/page.tsx`, `lsat-static/app/globals.css`
  - `lsat-static/components/{Drill,QuestionCard,Writing}.tsx`
  - `lsat-static/components/solve/SolveAssist.tsx`
- **Steps**:
  1. A shared `useShortcuts` hook with three invariants: never steal a keystroke from a text field (the writing editor is a 35-minute essay), never double-fire (skip an event a component handler already `preventDefault`ed), never shadow the browser (bare keys only; `mod+` and an explicit `allowWhileTyping` list are the two opt-ins).
  2. Bind every step of a drill: `A`–`E` select from anywhere on the page, `Enter` checks then advances, `N`/`P` move between questions, `H` opens and walks the hints, `J`/`K` move within revealed hints, `R` reveals the final step once graded.
  3. Bind Writing: `O` opens the first prompt, `T` starts/pauses the clock, `Ctrl`/`⌘`+`Enter` submits from inside the editor, `M` toggles the model response, `Escape` leaves the field and then the workspace.
  4. Global `[` / `]` for section movement (arrows stay with the radiogroup) and `?` for the reference dialog, with modal suspension so the page behind the dialog stops answering keys.
  5. Discoverability: a `?` dialog with focus trap and focus restore, a footer affordance, and `aria-keyshortcuts` on the controls the bindings drive.
- **Verify** (driven with real key events in a browser at 1280x900 and 390x844):
  - LR, RC, and LG each complete a question by keyboard alone: select → check → hint → advance.
  - `Enter` checks, then advances; with nothing selected it is a no-op.
  - `H` walks 1→2→3, `J`/`K` move within revealed steps, `R` jumps to 5 of 5.
  - Typing `n p t m o a h ] [ ?` inside the writing editor changes nothing.
  - `Ctrl+Enter` submits from inside the editor; `Escape` blurs then exits.
  - `]` while the help dialog is open does not move section.
  - `make ux-audit` (75 files) and `make lsat-static-build` clean.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make typecheck && make test && make lint-specs` green.
- LegalBench delta recorded in the PR description — expected 0 pp, harness untouched (spec §11).
- Provenance logging verified for `LSATWritingEvaluator` and, in slice 7, `LSATDraftJudge`.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260831-26 — test-gap, med — The static Writing view ships with no component test because `lsat-static` still has no test runner (BL-20260831-18); its timer, `localStorage` draft persistence, and model-response reveal-gating are verified only structurally by the root suite and by hand.
- BL-20260831-27 — feature, med — `LSATWritingEvaluator` scores a draft but nothing stores the result, so a learner cannot see progress across attempts the way `lsat_grade` powers MCQ stats; persist evaluations and fold writing practice into the stats surface.
- BL-20260831-28 — feature, low — The writing prompt library is hand-authored; the content factory has no writing archetypes and no coverage census for `WS`, so the slice 7 loop cannot grow the writing section the way it grows the MCQ bank.
- BL-20260831-29 — doc-gap, low — `docs/architecture.md` describes the LSAT module as three multiple-choice sections; it needs the writing content type and the `writing.py` loader alongside `bank.py` and `guides.py`.
