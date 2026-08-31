# Plan: Composite-widget keyboard accessibility

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: ship the shared keyboard *mechanism* (not a component layer), migrate the two broken widgets onto it, and gate both halves of the pattern.

## 1. Architecture

### Mechanism, not components

Spec 039 FR-4 owns the `Choice` / `Tabs` **component** API. Building those here would pre-empt it and create an API to reconcile later. What the two broken widgets actually lacked is smaller and lower in the stack: the roving-tabindex keyboard behaviour. So this ships a hook, and 039's components can wrap it unchanged.

Placement follows what is already there rather than inventing a location: pure logic in `frontend/lib/shell/` beside `shortcuts.ts` and `panels.ts` (the other interaction-contract modules), the React hook in `frontend/components/shell/` beside `useMediaQuery.ts`.

### Selection follows focus

Both widgets activate on arrow, matching `lsat-static/components/QuestionCard.tsx`. The APG permits it for tabs and specifies it for radiogroups, and the static drill already trained users on it. Two products diverging on the same widget would be worse than either choice alone.

### The letter stays in the name

The static site marks the choice letter `aria-hidden`. This spec deliberately does not: in a drill the letter *is* the answer's identity — what a student records, and what the tutor refers back to. An existing test (`LsatLab.test.tsx`, finding a radio by `/A.*Alpha/`) already encoded that expectation, and it caught the change when it was briefly made.

### Files

```
frontend/lib/shell/rovingFocus.ts               NEW  pure key -> next index
frontend/components/shell/useRovingTabIndex.ts  NEW  one tab stop + arrows
frontend/components/LsatLab.tsx                 EDIT tabs pattern + radiogroup + tutor input label
frontend/components/KnowledgeGraph.tsx          EDIT case-search label
frontend/components/GraphViewer.tsx             EDIT named role="img" region
frontend/components/AgentDashboard.tsx          EDIT run-filter label
frontend/app/icon.svg                           NEW  app icon
frontend/app/layout.tsx                         EDIT drop the dead favicon reference
scripts/ux_audit.py                             EDIT R10, R11, brace-aware JSX scanner
frontend/__tests__/shell/rovingFocus.test.tsx   NEW  behaviour half of the gate
docs/{ui-ux,ui-ux-review}.md, frontend/ui/README.md
                                                EDIT catalog + rules + pass log
```

## 2. Why the gate is split in two

A static rule can see whether `role="tab"` carries `aria-controls`; it cannot see whether an arrow key moves focus. Gating only the attributes would let a widget keep the ARIA and lose the behaviour, which is the more damaging half.

- **R10 / R11** (static, stdlib, CI): the declarative half — group names, tab/panel association, control names.
- **`rovingFocus.test.tsx`** (RTL): the behavioural half — one tab stop, arrows move and select, wrap, Home/End, orientation, modifier chords, and the not-yet-selected case.

R11's scanner balances `{}` and quotes rather than regexing to the next `>`. That is not fussiness: the naive form truncates at the `>` in `onChange={(e) => …}` and reports correctly-labelled controls as unlabelled — verified while writing this, and exactly the false-positive class the review doc says gets a rule deleted.

## 3. Test strategy

| Layer | Covers |
|-------|--------|
| `__tests__/shell/rovingFocus.test.tsx` | `nextRovingIndex` (orientation, wrap, Home/End, modifiers, empty group, no-loop) and `useRovingTabIndex` (single tab stop, arrow move + activate, wrap, unselected group reachable) |
| `__tests__/components/LsatLab.test.tsx` (existing) | Kept passing unchanged — it is the regression guard for the choice letter staying in the accessible name |
| `scripts/ux_audit.py` R10/R11 | Every file, forever |
| Real browser (Chromium via Playwright) | The layout/keyboard behaviour jsdom cannot prove |

## 4. Rollout

Single commit onto the spec 041 branch. It depends on `frontend/ui/` and `scripts/ux_audit.py` existing, so it cannot land independently of #90.

## 5. Risks

Carried from [spec.md](spec.md) §13. Two regressions were introduced and caught by the existing suite during implementation — `GraphViewer` treating `{nodes, edges}` as an array, and the choice letter briefly leaving the accessible name — which is the argument for running the full suite rather than only the new tests.
