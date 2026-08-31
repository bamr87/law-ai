# Spec: Interactive LSAT solving aids — progressive hints + incremental diagrams

- **ID**: 045-lsat-solving-aids
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-30
- **Roadmap Epic**: LSAT Lab evolution (specs 005 → 019 → 024 → 025 → this); user request 2026-08-30 "interactive and dynamic practice test system".
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No new runtime npm dependencies (diagrams are inline SVG + first-party components). No new LLM vendor. Any LLM call routes through `law_ai.core.llm`; guide *content generation* lands in the existing HITL proposal queue (§5). LegalBench untouched.

## 1. Problem & Motivation

The LSAT Lab grades answers and offers a post-hoc AI tutor, but gives a stuck user nothing *between* "reread the stem" and "reveal the explanation". Real LSAT pedagogy is incremental: inventory the elements, symbolize each rule, sketch the board, chain the inferences, and only then attack the choices. Today that method exists in the product only as prose inside tutor `next_steps`.

Concretely missing:

- **No hint system.** `Question.explanation` is all-or-nothing and only arrives after grading (`POST /api/lsat/grade`).
- **No diagramming.** Zero SVG/canvas code in any LSAT surface — Logic Games setups render as raw text rules; Logical Reasoning stimuli have no argument-structure view; Reading Comprehension passages have no structural map.
- **No incremental representation.** A user cannot ask "show me just the first move" — the sequence of elements written out, or one rule turned into symbolic notation — and then try again on their own.

The goal: each question carries a structured, machine-renderable **solve guide** — an ordered list of steps, each optionally paired with a typed diagram payload — that the UI reveals one stage at a time, so the practice test becomes an interactive coach rather than a static quiz.

## 2. Origin & Background

- Backlog items claimed: **BL-20260830-10** (interactive problem-solving aids: progressive hints, symbolic notation, LG boards, LR argument maps).
- Related open items *not* claimed (deliberately left to their own cycles): BL-20260702-13 (radiogroup roving tabindex — spec 039 `Choice` primitive), BL-20260503-03 (SSE streaming tutor), BL-20260830-02 (LsatLab decomposition).
- Constitution §13: LSAT content is pedagogical, not legal authority — no ranking/scoring of legal sources is involved. Who is the stronger? Test-prep incumbents monetize exactly this gap: method instruction locked behind paywalls. Shipping structured solving method as inspectable data (with provenance on every LLM-drafted guide) serves the test-taker, not the platform; guides always show *why* a step follows, never just "trust the answer".

## 3. Non-Goals

- NG1: No freehand drawing/whiteboard canvas for users (a scratchpad where users draw their own diagrams is a follow-up, not this cycle).
- NG2: No per-user persistence of hint usage (needs spec 036 accounts; hint reveals are audit events only, like grades today).
- NG3: No changes to the `lsat-static` site (unification tracked by BL-20260830-04; the static drill keeps its current behavior).
- NG4: No new charting/diagram npm library — Cytoscape stays graph-page-only; LSAT diagrams are first-party SVG/DOM.
- NG5: No autogeneration of guides directly into the bank — LLM-drafted guides go through the existing HITL proposal review flow, exactly like LLM-drafted questions.
- NG6: No Writing Sample section support (BL-20260503-04 stays open).

## 4. User Stories

- As a test-taker stuck on a Logic Game, I want to reveal *only* the element inventory (the sequence of entities and slots written out), so I can retry the setup myself before seeing more.
- As a test-taker who mis-symbolized a conditional rule, I want to see each rule rendered in standard arrow notation (`S → ¬T`, contrapositive shown) one rule at a time, so I learn the notation instead of the answer.
- As a visual learner on a Logical Reasoning question, I want the argument drawn as premises supporting a conclusion, so I can spot the gap the correct answer exploits.
- As a Reading Comprehension user, I want a paragraph-by-paragraph structural map (role of each paragraph), revealed incrementally, so I can practice mapping passages.
- As a self-directed learner, I want the UI to record that I used N hints on a question, so my session stats reflect assisted vs. unassisted accuracy.
- As a content reviewer, I want LLM-drafted solve guides to arrive in the same proposals queue I already review, so quality control stays human-gated.

## 5. Functional Requirements

- **FR-1 (guide schema)**: A Pydantic `SolveGuide` model in `backend/law_ai/lsat/services/guides.py`: `{question_id, method, steps: [SolveStep], version, source}`. `SolveStep = {kind, title, text, representation?, spoiler}` where `kind ∈ {orient, inventory, symbolize, diagram, infer, eliminate, answer}` and `spoiler: bool` marks steps that give away the correct choice (every `answer`-kind step is spoiler; others may be).
- **FR-2 (typed representations)**: `SolveStep.representation` is a discriminated union (`rep_type` discriminator) of: `sequence` (ordered slots + entities + fixed/excluded placements), `grid` (rows × columns assignment/grouping board with cell marks), `notation` (list of `{rule_text, symbols, note?}` symbolized rules), `argument_map` (nodes `{id, role ∈ premise|conclusion|assumption|objection, text}` + edges `{from, to, relation ∈ supports|opposes}`), `passage_map` (ordered `{paragraph, role, gist}`). Unknown `rep_type` values are rejected at load time.
- **FR-3 (seed content)**: Hand-authored guides in `backend/law_ai/lsat/services/data/guides.json` covering ≥ 9 bank questions spanning all three sections (≥ 3 LG with `sequence`/`grid`/`notation`, ≥ 3 LR with `argument_map`/`notation`, ≥ 3 RC with `passage_map`), each with ≥ 4 steps. A loader `load_guides()` (`@lru_cache`, mirrors `bank.py` loaders) validates all guides against the bank (every `question_id` must exist; guides for missing questions fail loudly).
- **FR-4 (hint endpoint)**: `GET /api/lsat/questions/<question_id>/guide` returns the guide with spoiler-step *content* withheld (`{kind, title, spoiler: true, locked: true}` stubs) by default; `?spoilers=1` returns full steps (client calls it only after the question is graded — same soft protection level as the existing grade endpoint). 404 with `{detail, has_tutor: true}` when no guide exists so the client can fall back to the tutor. Auth: `RequireLsat`, same as all `/api/lsat/*`.
- **FR-5 (hint audit)**: Each guide fetch emits a `lsat_guide` audit event (question_id, section, spoilers flag) via the same `law_ai.core` audit path as `lsat_grade`; the frontend reports step-reveal depth on grade via a new optional `hints_used: int` field on `GradeRequest`, which is recorded in the `lsat_grade` event and surfaced by `/api/lsat/stats` as `assisted` counts per section.
- **FR-6 (progressive reveal UI)**: A `SolveAssist` component (own file, not added to the `LsatLab.tsx` monolith) mounted inside `QuestionCard`: "Hint" button reveals steps one at a time; revealed count persists per question for the session; spoiler steps stay locked until the question is graded, then unlock with an explicit "Show final step" action. Keyboard accessible (button semantics, `aria-expanded`, revealed steps in an `aria-live="polite"` region).
- **FR-7 (diagram renderers)**: First-party renderers under `frontend/components/lsat/diagrams/`: `SequenceBoard` (SVG slots + entity chips), `GroupGrid` (table-based board), `RuleNotation` (semantic monospace notation with a legend for `→`, `¬`, `—`), `ArgumentMap` (SVG boxes + arrows, premises → conclusion), `PassageMap` (ordered role list). Each takes exactly its FR-2 payload type; all render legibly in the app's dark theme and at 320 px width (horizontal scroll inside the container, never the page).
- **FR-8 (tutor fallback + integration)**: When a question has no guide, `SolveAssist` offers the existing tutor ("Ask the AI tutor for a walkthrough"). `TutorPane` gains a "walkthrough" entry point that passes `user_question = "Walk me through the setup step by step without revealing the answer."` — no tutor API changes required.
- **FR-9 (guide authoring agent)**: `LSATSolveGuideAuthor` crew member (`backend/law_ai/agents_runtime/crews/lsat_solve_guide_author.py`, registered in `registry.py`) with `run(input: dict) -> dict`: given a `question_id`, drafts a `SolveGuide` (validated against FR-1/FR-2 schemas) via `law_ai.core.llm.agenerate(..., agent="lsat_guide_author")` with a versioned prompt file `prompts/lsat_solve_guide_author.v1.md`. Drafts enter the existing proposals JSONL store with a new `proposal_kind: "guide"` field; approve promotes into `guides.json` via `promote_guide_to_bank()`. `POST /api/lsat/guides/generate` (throttle scope `llm`) triggers it; HITL approval is mandatory before a draft ever serves on FR-4.
- **FR-11 (guide quality validation)**: A deterministic content validator `validate_guide_quality(guide, question)` in `guides.py`, run at every choke point a guide passes through — LLM draft parsing (`LSATSolveGuideAuthor`), HITL promotion (`promote_guide_to_bank`), and content load (`load_guides`). Checks beyond the Pydantic schema: the final step is an `answer` step that names the question's real correct choice; no non-spoiler step names the correct choice early (leak patterns) or performs complete elimination (rules out all four wrong choices — pins the answer by omission); `sequence`/`grid` payloads are internally consistent (placements/exclusions/cells reference declared slots, entities, rows, columns). A failing LLM draft degrades to the offline fallback; a failing promotion raises; a failing seed guide breaks tests/CI, never a user request.
- **FR-12 (concept-only references in the answer component)**: The post-grade answer area of `QuestionCard` carries **no author-rationale block and no external links**. The `question.references` URLs are never rendered there; the only references shown after submission resolve to the in-app concept catalog — concept name, summary, and the schema-level examples the question derives from (`ConceptRefs`). Unresolvable concept ids degrade to plain id chips. Method teaching remains the job of `SolveAssist` (FR-6) and the tutor (FR-8). Concept- and section-level reference links on the Concepts/Overview tabs are unaffected.
- **FR-13 (walkthrough persistence)**: LLM-produced tutor walkthroughs are stored in a keyed response cache (`services/llm_cache.py`, append-only JSONL, key = question + learner choice + follow-up + prompt version). An identical repeat request serves the stored copy (`cached: true`) with **no** new model call; offline fallbacks are never cached (the chain is retried instead); `refresh: true` forces regeneration. Cache hits still write the `lsat_tutor` audit event with a `cached` flag.
- **FR-14 (answer cross-check)**: `POST /api/lsat/questions/<id>/cross-check` (throttle scope `llm`) has the provider chain solve the question **blind** — the prompt carries stem/passage/choices but never the answer key — and compares the model's pick to the key. Agreement is reported as corroboration by a named model, never as verification (§13); disagreement sets `requires_human_review` and is flagged for a human to re-verify the key. Verdicts are cached per FR-13 (`refresh` re-solves); every run writes an `lsat_cross_check` audit event. Offline: an honest "unavailable" result, never a fabricated verdict.
- **FR-15 (question-set review)**: `GET /api/lsat/validation` returns a deterministic (no-model-call) accuracy report over the bank: per-question integrity issues (explanation never names the key, unknown concepts, broken passage links, guide-quality problems), answer-key distribution per section (reported as counts, never judged), and a roll-up of all stored FR-14 verdicts with each disagreement listed by question. Rendered on the Authoring tab (`ValidationReport`); the cross-check UI lives on graded question cards (`CrossCheckPanel`).
- **FR-10 (API client + types)**: `frontend/lib/api.ts` gains `LsatSolveGuide`, `LsatSolveStep`, representation payload types mirroring FR-2, `fetchLsatGuide(questionId, opts?)`, and `hints_used` on the grade call; MSW handlers for the new routes are added to the *shared* `frontend/mocks/server.ts` (with fixtures) rather than per-test-file.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: Guide fetch is file-backed + cached — p95 < 100 ms locally; diagram renderers use no external network or fonts; no new npm runtime deps.
- **NFR-SEC-1**: `question_id` path input validated (404 on unknown, no reflection); `hints_used` bounded 0–20 via the same `_bounded_int` pattern; guide endpoints sit behind `RequireLsat`.
- **NFR-AUDIT-1**: All `lsat_guide` fetches and guide-author LLM calls are logged (audit JSONL + `llm_call` provenance via `law_ai.core.llm`); the agent never calls a provider transport directly.
- **NFR-HITL-1**: `human_approval_required: true` for the FR-9 generation path — LLM-drafted guides serve users only after explicit approval in the proposals queue. FR-3 hand-authored seed guides are reviewed via normal PR review.
- **NFR-TEST-1**: Backend: unit tests for guide loading/validation, endpoint (spoiler stripping, 404 fallback, audit emission, `hints_used` stats), agent contract test in `backend/tests/agents/`. Frontend: Vitest + RTL for `SolveAssist` reveal flow and each diagram renderer. Coverage ≥ 75% on changed files.
- **NFR-A11Y-1**: Diagrams carry text alternatives (`role="img"` + `aria-label` summarizing the board; notation legend rendered as real text); reveal controls are buttons; no information conveyed by color alone (correct/incorrect marks use symbols + color).
- **NFR-DOCS-1**: [docs/agent-roles.md](../../docs/agent-roles.md) gains `LSATSolveGuideAuthor`; spec 005's LSAT Lab description references the guide system.

## 7. Data Model Impact

None in Postgres/Neo4j. New file-backed store `backend/law_ai/lsat/services/data/guides.json` (same pattern as `lr_bank.json` etc.). Proposals JSONL rows gain an optional `proposal_kind` field (default `"question"`, back-compatible replay).

## 8. API Surface

| Route | Method | Request | Response |
|---|---|---|---|
| `/api/lsat/questions/<id>/guide` | GET | `?spoilers=0\|1` | `SolveGuidePublic` (spoiler stubs unless `spoilers=1`); 404 `{detail, has_tutor}` |
| `/api/lsat/grade` | POST | `GradeRequest` + optional `hints_used` | unchanged `GradeResponse` |
| `/api/lsat/stats` | GET | unchanged | adds `assisted` / `unassisted` attempt counts per bucket |
| `/api/lsat/guides/generate` | POST | `{question_id}` | `{proposal, trace_id, model, degraded}` (throttle scope `llm`) |

Pydantic models by name: `SolveGuide`, `SolveStep`, `SequenceRep`, `GridRep`, `NotationRep`, `ArgumentMapRep`, `PassageMapRep`, `GenerateGuideRequest`.

## 9. Agent / Crew Impact

- New: `LSATSolveGuideAuthor` (FR-9) — versioned prompt `lsat_solve_guide_author.v1.md`, registered in `agents_runtime/registry.py`, output validated against `SolveGuide`, drafts HITL-gated.
- Modified: none. `LsatTutor` service untouched (FR-8 reuses the existing request shape).

## 10. Acceptance Criteria

- **AC-1**: `load_guides()` rejects a guide whose `question_id` is not in the bank, whose step list is empty, or whose representation has an unknown `rep_type`; all shipped seed guides load cleanly in tests.
- **AC-2**: `GET /api/lsat/questions/<id>/guide` withholds spoiler-step text by default and returns it with `?spoilers=1`; an unknown or guide-less question id returns 404 with `has_tutor: true`; every call emits an `lsat_guide` audit event.
- **AC-3**: Grading with `hints_used: 3` records it in the audit event, and `/api/lsat/stats` reports the attempt under `assisted`.
- **AC-4**: In the Lab, clicking "Hint" reveals exactly one more step per click; spoiler steps render as locked stubs until the question is graded; after grading, "Show final step" reveals them (RTL test).
- **AC-5**: Each of the five renderers displays its FR-2 payload: `SequenceBoard` shows ordered slots with placed/excluded entities; `RuleNotation` shows symbol strings with a legend; `ArgumentMap` draws premise→conclusion arrows; `GroupGrid` renders the board as an accessible table; `PassageMap` lists paragraph roles (RTL tests, one per renderer).
- **AC-6**: `LSATSolveGuideAuthor.run({"question_id": …})` returns a dict whose `guide` validates as `SolveGuide`; the draft appears in `GET /api/lsat/proposals` with `proposal_kind: "guide"` and never appears on the FR-4 endpoint until approved (agent test + API test).
- **AC-7**: `make lint`, `make typecheck`, `make test` green; `python3 scripts/spec_validator.py specs/045-lsat-solving-aids` exits 0.
- **AC-9**: After grading a question in the Lab, the DOM contains no "Author rationale" text, no rendered `question.references` anchors, and no external links in the answer area; a "Derived from" block lists the question's concepts with catalog-resolved name/summary/examples (RTL tests on `ConceptRefs` and the Lab grade flow).
- **AC-10**: Two identical tutor requests produce exactly one LLM call; the second response has `cached: true` with identical coaching; `refresh: true` forces a second call; an offline-fallback response is not cached and the next request retries the chain (endpoint tests assert mock call counts).
- **AC-11**: Cross-checking a question whose blind solve matches the key returns `agree: true` / no review flag; a mismatched solve returns `agree: false` + `requires_human_review: true` and an `lsat_cross_check` audit event; repeat checks serve the cached verdict; offline returns `model_choice: null`, `agree: null`, and an explicit "unavailable" rationale.
- **AC-12**: `GET /api/lsat/validation` reports `question_count` equal to the bank size, an answer distribution summing to it, and — after a disagreeing cross-check — lists that question under `cross_checks.disagreements`; the Authoring tab renders the report (RTL test).
- **AC-8**: `validate_guide_quality` rejects a guide that names the correct choice in a non-spoiler step, a non-spoiler step performing complete elimination, an answer step that never names the correct choice, and a sequence board placing an undeclared entity/slot; an LLM draft with any of these degrades (`degraded: true`, confidence 0.0) instead of entering the queue as a plausible draft; every shipped seed guide passes with zero problems (unit + agent tests).

## 11. LegalBench Impact

- Tasks affected: none (LSAT surfaces only; LegalBench harness untouched, still pinned to Ollama).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: `LsatLab.tsx` is already a 1611-line god component (BL-20260830-02). Mitigation: all new UI ships as separate files under `frontend/components/lsat/`; `LsatLab.tsx` only gains mount points.
- **R-2**: Hand-authored guide quality — a wrong symbolization teaches the wrong method. Mitigation: seed guides reviewed in PR; schema forces explicit rule-to-symbol pairing so errors are visible in review.
- **R-3**: Spoiler protection is soft (any client can pass `?spoilers=1`). Accepted: identical to the existing grade-endpoint exposure; real enforcement needs spec 036 accounts.

- **Resolved OQ-1** (2026-08-30): No penalty and no score arithmetic invention — the header session score gains a separate `assisted` count (e.g. `7/10 · 3 assisted`), mirroring the honest-labelling rule (§13: report what happened, don't editorialize it into a modified score). Stats bucket split per FR-5 stands.
- **Resolved OQ-2** (2026-08-30): Single-question generation this cycle. Bounded LLM budget, mirrors the reviewer's one-at-a-time approval flow; batch drafting for guide-less questions is a follow-up (§13 list).
- **Resolved OQ-3** (2026-08-30): Horizontal slot orientation for `sequence` boards — standard prep-book convention for ordering games and the natural fit for a scrollable container at 320 px (FR-7). No orientation option this cycle.

## 13. Out of Scope / Follow-ups

- User-drawn scratchpad canvas (NG1) — future spec.
- Per-user hint history in Postgres once spec 036 lands.
- Porting `SolveAssist` + renderers into `lsat-static` (join with BL-20260830-04 unification).
- Animated step-through (auto-play of board construction).
