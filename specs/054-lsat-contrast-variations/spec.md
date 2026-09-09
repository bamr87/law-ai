# Spec: LSAT Contrast Variations and the Agent Quality Loop

- **ID**: 054-lsat-contrast-variations
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-08
- **Roadmap Epic**: LSAT continuous curriculum ([specs/047](../047-lsat-continuous-curriculum/spec.md)) — builds directly on [specs/053](../053-lsat-question-diagnosis/spec.md)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

Spec 053 taught learners to name a question's type before answering it. The next thing a strong test-taker knows is how the *task* moves the answer: the same argument, weakened and then strengthened, has keys that are mirror images of one another; asked for its necessary assumption it wants a modest claim, asked for a sufficient one it wants a strong bridge. No article shows that as well as two items on the same stimulus do, side by side. The bank had no such pairs and no notion of a question being a variation of another.

The second gap is quality. The bank grows through agents, and spec 053 stamped every item's type with a rule. The judge tier existed but was advisory: a `fail` rode on the proposal and changed nothing, so a reviewer was shown exactly the draft the judge had torn apart. Nothing checked the type stamps with anything but the rule that wrote them. This spec adds **contrast variations** as a content type, an agent to author them, and the review machinery the user asked for: deterministic gates, an adversarial judge, a revise loop that hands objections back to the author, and a second agent that blind-reads type stamps and queues disagreements for a human.

## 2. Origin & Background

- Backlog items claimed: none — direct request ("create variations of the same question that incorporate a different strategy and concept to show parallels and teach the differences; make sure AI agents are wired in to review/validate/improve the quality of the questions").
- Prior art: [specs/019](../019-lsat-content-autogen/spec.md) (`LSATContentAuthor`, the HITL proposal queue), [specs/024](../024-lsat-content-factory/spec.md) (archetype taxonomy, `LSATDraftJudge`, intake gates), [specs/045](../045-lsat-solving-aids/spec.md) (its rule that nothing post-grade links out; the contrast panel links only inward), [specs/053](../053-lsat-question-diagnosis/spec.md) (playbooks, cue classifier, stamps). The cross-check sweep (BL-20260831-21) is the pattern the type-review sweep copies.
- **Review question (constitution §13)**: no — this feature ranks and reviews LSAT practice items, never legal authority.

## 3. Goals

- G1: A contrast set — a root question plus variations that keep its stimulus verbatim and re-ask it as other archetypes — as a first-class bank relationship, with a learner-facing note per variation on what changed.
- G2: An agent that authors variations and accepts a critique, so its drafts can be improved rather than merely annotated.
- G3: A review loop — deterministic gates, the adversarial judge, bounded revision — whose full history a human reviewer sees before deciding.
- G4: An agent that validates the spec 053 type stamps blind and queues disagreements for a human, with approval restamping and rejection keeping.
- G5: Nothing reaches the bank without a human; every agent call is logged through `core.provenance`.

## 4. Non-Goals

- NG1: Variations for passage-bound sections (RC, LG); their passage stacks already carry several types on one context. The service is section-generic; the author and sweep are LR-only in this release.
- NG2: Wiring the revise loop into the main factory's executors, whose author has no critique input yet.
- NG3: Auto-promotion on an accepted draft. Constitution §5 stands.
- NG4: Static-site parity for the contrast panel.

## 5. User Stories

- As a learner who just weakened an argument, I want to be offered the same argument as a Strengthen and as a Necessary Assumption question, with a note on where the key moved, so that I learn the task rather than the topic.
- As a reviewer, I want a variation draft to arrive with the objections each round raised and whether the final draft satisfied them, so that I review what the judge could not settle instead of what the model first wrote.
- As a content maintainer, I want a model's blind read of every question's type compared with the stamp, and disagreements queued where I already review, so that the diagnosis exercise's answer key is checked by something other than the rule that wrote it.

## 6. Functional Requirements

- **FR-1**: `Question` gains `variation_of` (root id) and `contrast_note`; the public question payload carries `variation_of` and never `contrast_note`. Three hand-authored variations ship (`lr-097`, `lr-098` of `lr-002`; `lr-099` of `lr-007`), each classifying as its stamp.
- **FR-2**: A contrast service: `stimulus_of` splits a stem into stimulus and question sentence; `contrast_set(id)` returns the root first from any member; `pivot_targets(q)` proposes types to re-ask as, the playbook's `confused_with` first, skipping types already in the set.
- **FR-3**: Deterministic variation gates (`validate_variation`): same section, target is not the source's type, stimulus preserved verbatim, question sentence changed, five distinct A–E choices, key not the source's key text, the stem classifies as the target type, concepts known and including the target's primary tag, a contrast note of at least sixty characters, trap ids known and never on the key, explanation present.
- **FR-4**: `LSATContrastAuthor` (crew, prompt `lsat_contrast_author.v1.md`): input `{question_id, target_archetype_id, critique[]}`; output a `ContrastDraft` (question fields plus `variation_of`, `target_archetype_id`, `contrast_note`, `distractor_traps`) or no draft when degraded — never an offline placeholder. Registered, `human_approval_required`, one provenance event per run.
- **FR-5**: `draft_variation(source, target)` runs the author through FR-3 and `LSATDraftJudge`, files the result as a pending `question` proposal with `meta.variation_of`, `meta.factory.archetype_id` (so promotion stamps it), `meta.factory.judge`, and `meta.revisions` (every round's gate issues, judge verdict and critique, plus `accepted`). An unaccepted draft is still filed, flagged; a degraded run files nothing.
- **FR-6**: A generic revise loop (`factory/revise.py`): author → gates → judge → critique → author, bounded by `max_rounds`; a `fail` verdict or a disagreeing blind key blocks and feeds back; a `flag` that names concrete issues also blocks while rounds remain and is accepted, as a named reservation for the reviewer, only on the final round; a malformed model answer is a round's objection, not an outage; a degraded judge never blocks; the cap returns the last draft unaccepted with its history.
- **FR-7**: Promotion carries `variation_of` and `contrast_note` into the bank item; `GET /api/lsat/questions/<id>/contrast` returns the set (notes only with `?spoilers=1`); `POST /api/lsat/questions/<id>/variations` runs FR-5 on demand (throttled, 202 with the outcome, 503 when degraded).
- **FR-8**: `LSATTypeReviewer` (crew, prompt `lsat_type_reviewer.v1.md`): blind-reads one question against the section's type menu, computes agreement with the stamp itself, caches per prompt version, degrades on outage or an off-menu pick. A `typecheck` proposal kind; `promote_typecheck` restamps the bank item on approval; rejection keeps the stamp.
- **FR-9**: Two sweeps with budget caps and dry runs: `lsat_contrast_sweep` (`--source`, `--target`, `--limit`, `--max-rounds`, `--no-judge`) and `lsat_type_review_sweep` (`--section`, `--limit`, `--refresh`), plus `make lsat-contrast-sweep` and `make lsat-type-review`. Degraded results are never filed; pending pairs are skipped.
- **FR-10**: Frontend: a post-grade contrast panel on the question card (the graded item's note, siblings with their tasks, sibling notes behind a disclosure, "try it" deep links); `/lsat?question=<id>` opens the LR drill on that question once; the Authoring tab renders type-check cards with "Restamp as X" / "Keep current stamp", shows lineage and the revision history on variation drafts, and offers a "draft a contrast variation" form.

- **FR-11**: A rewrite loop for existing bank items: `LSATDraftJudge` attacks each item as it stands (verdict cached per prompt version); a clean verdict files nothing; an objection runs `LSATQuestionEditor` (crew, prompt `lsat_question_editor.v1.md`, takes a critique) through `validate_rewrite` (same section, still classifies as the stamped type, five distinct choices, known concepts, a change summary, and the stimulus verbatim when a contrast set shares it) → judge → revise, and files a pending `rewrite` proposal with `meta.rewrite_of`, `meta.original_judge`, `meta.revisions` and `meta.final_review`. `promote_rewrite` replaces the item **in place** (id, section, stamp, lineage and passage link unchanged; a review record names the approver). `lsat_question_review_sweep` (`--section`, `--limit`, `--max-rounds`, `--no-final`, `--refresh`, `--dry-run`), `make lsat-question-review`, and `POST /api/lsat/questions/<id>/review`.
- **FR-12**: A final review stage, wired into both loops: every accepted draft is judged once more by `LSATDraftJudge` pinned to the final-review model (`LSAT_FINAL_REVIEW_MODEL`, default `claude-fable-5-1`, both Claude tiers overridden). Its verdict is recorded as `meta.final_review`; a `fail` or a disagreeing key files the draft unaccepted without another round; a `flag` is a reservation for the reviewer. The Authoring tab shows it as a badge on variation and rewrite cards.

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: Every author, judge and reviewer run writes one `agent_call` through `core.provenance`; every model call writes `llm_call` via `law_ai.core.llm`; every HITL decision is audited by `set_status` as before.
- **NFR-HITL-1**: Both new crews declare `human_approval_required`; no path writes to the bank except `promote_to_bank` and `promote_typecheck`, both reviewer-invoked.
- **NFR-SPOILER-1**: `contrast_note` and `archetype` never appear in a question payload; the contrast endpoint withholds notes unless asked after grading.
- **NFR-DEGRADE-1**: No provider means no draft and no filed row; a degraded judge decides nothing.

## 8. Data Model Impact

- Bank items: optional `variation_of`, `contrast_note`; three new LR items.
- Proposal store: new kind `typecheck`; `meta.variation_of`, `meta.revisions` on variation drafts. No Postgres migration (the mirror stores `payload` verbatim).
- Response cache: new kind `typecheck`.

## 9. API Surface

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/api/lsat/questions/<id>/contrast?spoilers=` | contrast set, root first |
| POST | `/api/lsat/questions/<id>/variations` | `{target_archetype_id, max_rounds?, use_judge?}` → 202 `VariationResult` / 503 degraded |
| POST | `/api/lsat/proposals/<id>/approve` | `typecheck` kind now restamps |

## 10. Agent / Crew Impact

New: `LSATContrastAuthor`, `LSATTypeReviewer` (both registered). Reused: `LSATDraftJudge` inside the revise loop. `docs/agent-roles.md` gains rows for all three (the judge's row was missing).

## 11. Acceptance Criteria

- **AC-1**: Every shipped variation shares its root's stimulus verbatim, has a different archetype from its root, classifies as its stamp, carries a note, and clears `validate_variation` against its root.
- **AC-2**: The contrast endpoint returns the set root-first from any member, without keys or notes, and with notes under `?spoilers=1`; a question payload names `variation_of` but never `archetype` or `contrast_note`.
- **AC-3**: With a faked author and judge, `draft_variation` files a pending `question` proposal carrying `variation_of`, the target archetype, the verdict and `revisions.accepted=True`.
- **AC-4**: Promoting that proposal writes an item with `variation_of`, `contrast_note` and the target `archetype`, and it appears in the root's contrast set.
- **AC-5**: A draft failing a gate is re-requested with the gate's objection as critique; at the cap the draft is filed with `revisions.accepted=False` and every round recorded; a degraded author files nothing.
- **AC-6**: The variations endpoint returns 422 for an unknown type, 404 for an unknown question, 202 with the outcome, and 503 when degraded.
- **AC-7**: The type reviewer computes `agrees` itself, is cached per prompt version, degrades on outage and on an off-menu pick, and never shows the stamp in its prompt; the sweep files a `typecheck` row on disagreement only and skips pending and cached items; approving restamps the bank item and rejecting keeps it.
- **AC-8**: The revise loop: accepts the first clean draft, feeds gate issues and judge objections to the next round, blocks on `fail`, on a disagreeing key, and on a `flag` with issues while rounds remain, accepts a persisting `flag` on the final round, ignores a degraded judge, and returns the last draft unaccepted at the cap.
- **AC-9**: The contrast panel shows the graded item's note, the siblings with tasks and "try it" links, keeps sibling notes closed by default, and renders nothing for a question with no variations; the authoring type-check card offers restamp and keep; a variation draft shows its lineage and revision history.

## 11a. Live validation (2026-09-08)

Full-bank runs of all three sweeps were started against the Claude Code OAuth tier with Fable (`claude-fable-5-1`) as the final reviewer; their queued rows are the reviewer's to approve or reject on the Authoring tab.

Run against the Claude Code OAuth tier (`LLM_PROVIDER_CHAIN=claude_code`, `claude-opus-5`):

- `lr-002 → lr-evaluate-argument`: one round; gates clean; judge `flag` with the key agreeing; filed as `prop-025b0f3666bf`.
- `lr-002 → lr-causal-flaw`: three rounds; round one the judge caught an unedited reference to the source's key ("the source's tolls fact") in the explanation, round two the model returned six choices and the shape error went back as critique, round three passed clean; filed as `prop-ac1263d57e36`.
- `lsat_type_review_sweep --section LR --limit 12`: eleven stamps confirmed, one disagreement queued (`lr-004`, stamped equivocation, read as general flaw) as `prop-c2a85f9346d2`.

All three sit pending on the Authoring tab; nothing was written to the bank. The first live run surfaced that the Messages API rejects a free-form map in a structured-output schema (400), which is why `distractor_traps` travels as a list of pairs.

- **AC-10**: Given a bank item the judge passes, `review_question` files nothing and the verdict is cached; given an objection, the editor's draft goes through the gates and the judge, the final reviewer's verdict is recorded, and a pending `rewrite` proposal exists carrying the original verdict and the history; promoting it replaces the item in place, keeping id and stamp, with an editorial review record; a final-review `fail` files it unaccepted; a degraded editor files nothing.
- **AC-11**: The rewrite gates reject a type change and a changed stimulus on a contrast-set member, and accept an unchanged-stimulus edit on a lone item; the sweep skips judged and pending items and reports clean, queued and flagged counts; the review endpoint returns 202 with the outcome and 503 when degraded.
- **AC-12**: The revise loop runs the final reviewer exactly once, only on an accepted draft; a final `flag` keeps acceptance and costs no round; a final `fail` un-accepts.

## 12. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 13. Risks & Open Questions

- **R-1**: A model may edit the stimulus subtly. Mitigation: the gate compares normalised stimulus text and sends the objection back; a reviewer still sees the diff.
- **R-2**: Judge and author could loop on an irreconcilable objection. Mitigation: the cap, and the unaccepted draft is still filed with its history rather than lost.
- **R-3**: Restamping on a model's read could overwrite a correct stamp. Mitigation: it is a human decision per row; the card shows the stamp, the cue read and the model read side by side.

## 14. Out of Scope / Follow-ups

- Static-site parity, RC/LG variations, the main-factory revise loop, autonomy beats for the two sweeps, and surfacing `human_approval_required` through the agents API — recorded in `tasks.md` and mirrored to `BACKLOG.md`.
