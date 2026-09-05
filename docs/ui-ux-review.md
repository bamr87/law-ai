# The UI/UX review loop

> A repeatable pass over Law AI's application shell, navigation, and interaction contract. Run it with `/ux-review` (see [.claude/commands/ux-review.md](../.claude/commands/ux-review.md)), on a `/loop` interval, or by hand. [docs/ui-ux.md](ui-ux.md) records **what the UI is**; this file defines **how we keep it good as the product grows**.

The loop exists because UI quality decays differently from correctness. Nothing fails when a new module forgets a loading state, ships an unnamed `<aside>`, or hard-codes `top-4` on a sticky bar. It just gets slightly worse, in a place nobody owns, until the shell is six idioms in a trench coat. So the review is a scheduled obligation with a mechanical floor, not a taste debate.

---

## How a pass works

One pass produces **one merged improvement**, not a list of complaints. Reviews that end in a backlog dump are how the backlog got long.

### 0. Orient (5 minutes, every pass)

Re-read what the product is for before judging how it feels, because the right UX for an audit-grade legal tool is not the right UX for a consumer app:

- [docs/constitution.md](constitution.md) — the non-negotiables the UI has to keep visible (provenance, HITL, UPL).
- [docs/ui-ux.md](ui-ux.md) — the current-state inventory.
- The **pass log** at the bottom of this file — what the previous pass already found, so this one starts where that one stopped.
- `git log --oneline -20 -- frontend/` — what shipped since the last pass. New functionality is where new gaps are.

### 1. Run the mechanical floor

```bash
make ux-audit            # scripts/ux_audit.py — 9 structural rules
python3 scripts/ux_audit.py --list
make test-frontend
```

The audit is the floor, not the ceiling: it proves nothing regressed structurally, and it fails the build in CI's Spec Drift Gate. If it is red, fixing it *is* the pass. See [The mechanical contract](#the-mechanical-contract) below.

### 2. Score the rubric

Walk the eight dimensions below over the routes that exist **today** (`frontend/app/(app)/`), scoring each 0–3:

| Score | Meaning |
|-------|---------|
| 0 | Absent — the app does not do this at all. |
| 1 | Partial — one or two screens do it, by hand. |
| 2 | Solid — every current screen does it. |
| 3 | Systematic — a shared primitive or gate makes it hard to get wrong on the *next* screen. |

Only 3 is finished. A dimension at 2 is a dimension that decays the moment someone adds a module, and "scalable" is exactly the difference between 2 and 3.

### 3. Pick one finding

Take the lowest-scoring dimension. Break the tie with, in order: a safety obligation (D8), something on the path a first-time user takes, then whatever affects the most routes.

### 4. Fix it through the normal chain

Non-trivial work goes through AO-SDLC (`/specify → /clarify → /plan → /tasks → /implement`). A one-file fix does not need a spec package, but it does need the same gates: `make lint`, `make typecheck`, `make test`, `make lint-specs`, and a §11 follow-up mirrored into [BACKLOG.md](../BACKLOG.md).

**Promote the fix into the floor.** If the fix could regress silently, it earns a rule in `scripts/ux_audit.py` or a test in `frontend/__tests__/shell/`. This is what moves a dimension from 2 to 3, and it is the part of the loop most worth doing.

### 5. Log the pass

Append a row to the [pass log](#pass-log). A loop with no memory re-litigates the same three findings forever.

### Stop conditions

Halt and surface to a human rather than proceeding when a pass would: change what the product claims about legal authority, remove or weaken a UPL disclaimer / HITL gate / provenance surface, add a runtime npm dependency, or redesign a feature's information model rather than its presentation. Those are product decisions wearing a UX costume.

---

## The rubric

### D1 — Orientation

Can a user say where they are, what this screen is for, and how they got here, at any scroll offset? Covers: breadcrumbs, active nav state that is not colour-only, document titles, the page header surviving scroll, and empty states that explain rather than apologise.

### D2 — Persistence and scroll

Does the chrome stay put and does content scroll in exactly one place? Covers: the viewport-locked shell, panels owning their own scroll, the sticky header/toolbar stack, per-route scroll memory, no scroll-chaining, no nested scrollbars, and `prefers-reduced-motion`.

### D3 — Navigation reach

Is every destination reachable in at most two actions, by mouse, by keyboard, and on a phone? Covers: the nav rail and its compact equivalent, the contextual sidebar, the ⌘K palette, shortcuts that never fire mid-sentence, deep-linkable view state (panels, tabs, filters), and Back doing what Back should.

### D4 — State completeness

Every async surface owes the user four states: loading, empty, error, and partial/degraded. Covers: skeletons over spinners, error boundaries that keep the shell alive, an empty state that names the next action, and a degraded state that says *what* is missing — "Neo4j unreachable" beats an empty canvas.

### D5 — Input and feedback

Does the user always know whether the system heard them? Covers: pending and disabled states on every submit, keyboard submit affordances, validation before the request, destructive-action confirmation, and never silently truncating input.

### D6 — Accessibility

Covers: one `<main>`, named landmarks, a visible `:focus-visible` ring on every interactive element, a working skip link, focus trapped in and restored from overlays, arrow-key navigation in composite widgets, WCAG AA contrast, and zoom that is not capped.

### D7 — Responsiveness

Does the app work at 360px as a first-class case rather than an apology? Covers: compact-viewport parity for panels (real drawers, not stubs), thumb-reachable primary navigation, no horizontal page scroll, tap targets ≥ 44px, and `dvh` rather than `vh` for anything viewport-sized.

### D8 — Domain integrity (Law AI specific)

The dimension a generic UX review would miss, and the one the constitution cares about most. Covers: the UPL disclaimer reachable from every surface that renders generated analysis; citations labelled verified/unverified rather than quietly presented as authority; confidence and graph node size never rendered so they read as correctness; HITL gates visible where they apply; provenance and trace links present on every agent output; absence-of-results never implied to mean absence-of-law.

Ask each pass: **who does this design advantage?** A more confident-looking UI advantages the operator over an under-resourced user who cannot tell a study aid from advice. That trade is never worth a nicer screenshot.

---

## Visual evidence

**Every change to `frontend/` or `lsat-static/` that a user could see ships with screenshots**, in the PR and — for anything worth keeping — committed under `docs/images/`. This is a gate, not a courtesy. `ux_audit.py` proves a `<nav>` has a name; it cannot tell you the heading is clipped, the column is a third of the monitor, or the page still advertises a tab that was removed. Only a picture does, and every one of those was caught by a screenshot rather than by a passing suite.

**What to capture**, at minimum:

- **The changed surface** at a normal laptop width (1440px is the house default).
- **Before and after**, side by side, whenever the change is layout, spacing, density or width. "It looks better" is not reviewable; two images are.
- **Each state you added or changed** — a new view, an empty state, an error state, a loading state. A view switcher means one shot per view.
- **The width the change is about.** A responsive change proven only at 1440px is not proven; capture the breakpoint it targets.

**How to capture it.** The app needs an API, so `make dev` is the straightforward route. When the backend cannot run, a stub that serves the real exported corpus (`lsat-static/content.json`) behind `NEXT_PUBLIC_API_BASE_URL` gives faithful content without inventing fixtures — screenshots of lorem ipsum hide exactly the overflow and truncation bugs you are looking for. Then drive Chromium with Playwright (pre-installed; pin `executablePath` if the browser build is older than the `@playwright/test` in `package.json`).

Three things that make a screenshot honest rather than decorative:

- Park `<main>` at `scrollTop = 0` before capturing. The shell is `h-dvh overflow-hidden` with one scroller, so a shot taken mid-scroll hides the sticky header and toolbar the change is usually about.
- Hide the dev overlay (`nextjs-portal { display: none }`). It is not part of the product.
- Use `reducedMotion: 'reduce'` and `await document.fonts.ready`, so the image is deterministic rather than whatever the animation happened to be doing.

**Naming.** `docs/images/<area>-<what>.png`, e.g. `lsat-library-concepts-view.png`, `lsat-library-width-before.png`. Reference them from the PR body with `https://raw.githubusercontent.com/bamr87/law-ai/<branch>/docs/images/<file>` — a repo-relative path does not render in a PR description.

**Look at what you captured before you attach it.** A screenshot you did not open is not evidence, and reading them is where the misses turn up.

---

## The mechanical contract

`scripts/ux_audit.py` enforces the structural rules — stdlib only, no container, runs in CI's Spec Drift Gate (which has no path filter, so it covers static-site-only changes too) and in `make lint-specs`.

**It audits both front ends.** The universal rules (R3–R6, R9–R11) hold everywhere: a landmark needs a name and a control needs a label in either app. The shell rules (R1, R2, R7, R8) describe chrome `lsat-static` does not have and are checked on `frontend/` only — holding a surface to rules it structurally cannot satisfy teaches everyone to ignore the audit. R4 and R9 additionally read stylesheets, because the static site writes its whole layout in CSS rather than in class strings.

| Rule | What it prevents |
|------|------------------|
| R1 | Ad-hoc `overflow-auto` instead of `.shell-scroll` / `.shell-panel-scroll` — nested scrollbars and scroll-chaining. |
| R2 | A screen claiming the viewport (`h-dvh`/`h-screen`) the shell owns — double scrollbars. |
| R3 | A second `<main>` landmark — breaks the skip link. |
| R4 | Literal z-indexes that fight the shell's `--z-*` scale. |
| R5 | `focus:outline-none` with no ring put back. |
| R6 | An unnamed `<nav>` / `<aside>`. |
| R7 | A route not using `PageLayout` — the sticky header and gutters are the frame, not a suggestion. |
| R8 | A route group with no `loading.tsx` / `error.tsx` / `not-found.tsx`. |
| R9 | A magic sticky `top-<n>` instead of the shell's sticky stack. |
| R10 | A `tablist`/`radiogroup` with no accessible name, or a `role="tab"` that names no panel. |
| R11 | A form control whose only name is its placeholder — it vanishes on the first keystroke. |
| R12 | The two copies of `frontend/ui/base.css` have drifted. Run `make ui-sync`. |
| R13 | A platform LSAT component with no `lsat-static` counterpart and no `static-parity: none — <reason>`. |

**Opting out.** Put `ux-audit: exempt — <reason>` in a comment to exempt a whole file, or `ux-audit: bare-page — <reason>` to exempt one route from R7. A reason is required on the same line, so every exemption explains itself to the next reader. Two exist today: `components/NavBar.tsx` (superseded dead code) and the dashboard route (full-bleed hero).

The keyboard half of a composite widget (one tab stop, arrows move within it) is behavioural and cannot be seen statically — `frontend/__tests__/shell/rovingFocus.test.tsx` covers that half.

**Adding a rule** is the normal outcome of a pass. Keep them zero-false-positive — a gate that cries wolf gets `--no-verify`'d and then deleted.

---

## The layout contract a new surface inherits

A new module should need none of this explained. Register it in `frontend/lib/modules/catalog.ts` and it gets nav rail placement, compact tab bar placement, breadcrumbs, contextual sidebar, inspector copy, and a ⌘K entry. Then:

- Wrap the route in `PageLayout` and pick a `width` — never hand-roll `mx-auto max-w-*`.
- Put repeatedly-used controls in a `StickyToolbar`; it parks itself on the stack.
- Scroll a list with `.shell-panel-scroll`, never `overflow-auto`.
- Take z-indexes from the `--z-*` scale in [frontend/ui/layout.css](../frontend/ui/layout.css).
- Put a focus ring on every control with `.focus-ring` (or `.focus-ring-practice` in LSAT contexts).

---

## Pass log

Append one row per pass. Keep it short; the diff is the detail.

| Date | Pass | Lowest dimension | Shipped | Promoted to the floor |
|------|------|------------------|---------|-----------------------|
| 2026-08-31 | 1 | D2 — persistence and scroll (0: chrome scrolled away with content) | specs/041 — viewport-locked shell, sticky page-header stack, per-route scroll memory, drawers, ⌘K palette, route states | `scripts/ux_audit.py` R1–R9 + `make ux-audit` in CI; 40 shell tests |
| 2026-08-31 | 2 | D6 — accessibility (1: composite widgets had no keyboard pattern) | LSAT tab bar and answer choices onto the WAI-ARIA roving-tabindex pattern via `useRovingTabIndex`; graph canvas + 3 placeholder-only controls named; favicon 404 fixed | `ux_audit.py` R10 + R11 (brace-aware JSX scanner) + 10 roving-focus tests |
| 2026-08-31 | 3 | Cross-surface drift — the audit covered `frontend/` only, so specs 041-043 never reached the published static site | specs/044 — shared `base.css` mirrored into `lsat-static`, skip link, one `contentinfo`, tokenised sticky stack that pins the section clock at ≥820px only | `ux_audit.py` R12 + both surfaces + stylesheet scanning; R3/R11 false positives fixed |
| 2026-08-31 | 4 | Feature drift — spec 045 shipped solving aids to the lab and nothing to the published site; a no-op Pages deploy made it look updated | specs/046 — guides in the export payload, hint carousel + 5 diagram renderers + concept refs ported, nav labels aligned, honest deploy filter | `ux_audit.py` R13 (ported, or declared `static-parity: none`) |
