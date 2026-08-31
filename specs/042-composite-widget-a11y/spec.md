# Spec: Composite-widget keyboard accessibility

- **ID**: 042-composite-widget-a11y
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: make the platform's interactive widgets as keyboard-accessible as the static site's
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No amendment needed — no dependency, no palette, no change to what the product claims.

## 1. Problem & Motivation

Pass 2 of the `/ux-review` loop scored **D6 (accessibility) at 1** and found that the platform's composite widgets announce roles they do not implement.

The LSAT Lab section switcher (`LsatLab.tsx`) declared `role="tablist"` with seven `role="tab"` children, and then: no `aria-controls` on any tab, no `role="tabpanel"` anywhere, every tab a separate tab stop, and arrow keys doing nothing. Verified in a real browser — ArrowRight moved neither focus nor selection, and crossing the bar took seven Tab presses. The answer-choice list declared `role="radiogroup"` with no accessible name, no roving tabindex, and no arrow-key handling.

`lsat-static/components/QuestionCard.tsx` — the same widget, in the export of the same product — has implemented roving tabindex, arrow selection-follows-focus, and a named group since spec 025. So the **API-backed primary surface was strictly less accessible than its static twin**, which is exactly the regression [docs/ui-ux.md](../../docs/ui-ux.md) finding #12 warned against.

The same sweep found three controls named only by a placeholder (graph case search, Agent Ops run filter, LSAT tutor follow-up), a Cytoscape canvas reaching screen readers as three anonymous `<canvas>` elements, and a `/favicon.ico` 404 on every page load.

This matters more here than in a generic app: the LSAT drill is used under exam-style time pressure, and a student who navigates by keyboard was paying five extra keystrokes per question that a mouse user was not.

## 2. Origin & Background

- Backlog items claimed: none. Surfaced by `/ux-review` pass 2 ([docs/ui-ux-review.md](../../docs/ui-ux-review.md)).
- Review question (constitution §13): this spec does **not** rank, score, or summarize legal authority. It changes keyboard and screen-reader affordances only.
- Who is the stronger here? A widget that looks operable and is not advantages the sighted mouse user over the keyboard and screen-reader user, on the surface (LSAT practice) most likely to be used by someone who is not yet a lawyer.

## 3. Goals

- G1: Every composite widget is one tab stop with arrow-key movement inside it.
- G2: The mechanism is shared, so the next widget inherits it rather than re-deriving it.
- G3: Every control and non-text region has an accessible name.
- G4: Both halves — the ARIA attributes and the keyboard behaviour — are gated so this cannot silently regress.

## 4. Non-Goals

- NG1: A `Choice` / `Tabs` **component** API — that stays spec 039's FR-4. This ships the mechanism (a hook), not the component layer.
- NG2: Decomposing `LsatLab.tsx` (BL-20260830-02).
- NG3: An accessible data-table alternative to the graph canvas beyond naming the region and pointing at the case list.
- NG4: Bringing `lsat-static` onto the shared hook.
- NG5: Touch-target sizing (all measured targets clear the WCAG 2.5.8 AA floor of 24px).

## 5. User Stories

- As a student drilling by keyboard, I want to Tab once into the section switcher and arrow between sections, so I am not paying seven keystrokes to reach a question.
- As a student using a screen reader, I want the answer list to announce itself as "Answer choices" and the letter to stay in each option's name, so I can record and discuss the answer I picked.
- As a screen-reader user on the graph, I want the canvas to say what it renders and point me at the equivalent list, rather than three unnamed graphics.
- As a contributor, I want a widget that declares `role="tab"` and forgets `aria-controls` to fail the build.

## 6. Functional Requirements

- **FR-1**: `nextRovingIndex` — a pure function mapping a key event to the next index in a composite widget, supporting horizontal/vertical/both orientation, wrap, and Home/End, and returning null for modified chords and keys it does not own.
- **FR-2**: `useRovingTabIndex` — a hook making a group one tab stop: exactly one item has `tabIndex=0`, arrows move focus and activate, and the group stays reachable when nothing is selected yet.
- **FR-3**: The LSAT section switcher implements the WAI-ARIA tabs pattern — `aria-controls` on every tab, a `role="tabpanel"` labelled by its tab and reachable at `tabIndex=0`, one tab stop, arrows move and select.
- **FR-4**: The LSAT answer list implements the radiogroup pattern — named group, vertical orientation, roving tabindex, arrows move and select. The choice **letter stays in each option's accessible name**: in a drill the letter is the answer's identity, not decoration.
- **FR-5**: Every form control has a name that is not its placeholder (graph case search, Agent Ops run filter, LSAT tutor follow-up).
- **FR-6**: The graph canvas is a named `role="img"` region reporting case and edge counts and naming the case list as its accessible equivalent.
- **FR-7**: The app serves an icon (`app/icon.svg`); the dead `/favicon.ico` metadata reference is removed.
- **FR-8**: `scripts/ux_audit.py` gains **R10** (composite groups are named; `role="tab"` carries `aria-controls`) and **R11** (no control is named only by its placeholder), both documented in the rule table.

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: The keyboard contract matches `lsat-static/components/QuestionCard.tsx` — selection follows focus — so the two products do not diverge on the same widget.
- **NFR-A11Y-2**: Arrow keys never fire from a modified chord (Ctrl/Cmd/Alt), and a horizontal group ignores vertical arrows and vice versa.
- **NFR-TEST-1**: R11's scanner is brace-aware. A naive `<input[^>]*>` regex truncates at the `>` inside `onChange={(e) => …}` and reports labelled controls as unlabelled; that false-positive class would get the rule deleted.
- **NFR-SEC-1**: No new runtime npm dependencies.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes.
- **NFR-HITL-1**: `human_approval_required` is false. Visual acceptance is the PR review.
- **NFR-DOCS-1**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, and `frontend/ui/README.md` record the shipped state and the new rules.

## 8. Data Model Impact

None.

## 9. API Surface

None. No backend routes.

## 10. Agent / Crew Impact

None to `agents_runtime`. Dev agents gain `useRovingTabIndex` in the `frontend/ui/README.md` catalog.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given the LSAT tab bar, when rendered, then exactly one tab has `tabIndex=0`, all seven carry `aria-controls`, and one `role="tabpanel"` is labelled by the active tab.
- **AC-2**: Given focus on a tab, when ArrowRight is pressed, then focus and `aria-selected` both move to the next tab and wrap at the end; Home/End jump to the first/last.
- **AC-3**: Given the answer list, when ArrowDown is pressed, then focus moves and that choice becomes checked; ArrowRight does nothing (vertical orientation); the group is named "Answer choices" and each option's name retains its letter.
- **AC-4**: Given a group where nothing is selected, when rendered, then one item is still `tabIndex=0` — an all-`-1` group is a keyboard dead end.
- **AC-5**: Given `python3 scripts/ux_audit.py`, when a composite group loses its name, a tab loses `aria-controls`, or a control is named only by its placeholder, then it exits 1 naming file, line, and rule; on the fixed tree it exits 0.
- **AC-6**: Given `make test-frontend`, then the roving-focus suite and every pre-existing suite pass.
- **AC-7**: Given a page load, then the browser console reports zero errors.

## 13. Risks & Open Questions

- **R-1**: Selection-follows-focus re-renders a panel on every arrow press. Mitigated: the LSAT panels are already mounted conditionally and cheap; the APG permits it, and matching the static site matters more than saving a render.
- **R-2**: R11 could fire on the implicit-`<label>`-wrapper idiom. Mitigated: only `placeholder`-bearing controls are flagged, and the brace-aware scanner was verified against all three real defects with zero false positives on the six correctly-labelled controls.
- **R-3**: Hiding the choice letter would have matched the static site but lost the answer's identity. Resolved deliberately in favour of keeping it — the static site's `aria-hidden` on that span is the weaker choice, and an existing test encoded the letter as intended.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG.
