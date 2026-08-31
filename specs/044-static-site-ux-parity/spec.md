# Spec: Static LSAT site UI/UX parity

- **ID**: 044-static-site-ux-parity
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: hold both front ends to one UI/UX contract
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No amendment needed; spec 039 NFR-PERF-1 (the static export stays Tailwind-free) is preserved and verified.

## 1. Problem & Motivation

Specs 041–043 raised the platform's shell, accessibility, and layout contract, and gated all of it in `scripts/ux_audit.py`. None of that reached `lsat-static/`, the GitHub Pages export that is the product's most public surface — so the two front ends drifted apart while the audit reported green.

Concretely, the static site had: no skip link (`main#view` was a ready focus target nothing pointed at), **two `contentinfo` landmarks** (the layout's UPL disclaimer plus a bare `<footer>` in the page — the same defect fixed on the platform homepage in spec 041), a hand-written `z-index: 10` and a magic `top: 5rem` where the platform now uses a token scale, and a section timer that scrolled out of view during a drill — the exact defect that motivated spec 043 on the platform.

It also carried a latent bug the platform had in the same shape: `.passage` is a grid item, so `align-self: stretch` made it exactly as tall as its row and its `position: sticky` did nothing at all.

Underneath those was the structural problem: `ux_audit.py` scanned `frontend/` only, and only `.tsx`. The static site expresses its entire layout in CSS, so even the rules that did apply were blind to it.

## 2. Origin & Background

- Backlog items claimed: **BL-20260831-04** (no skip link; does not consume the shared primitives).
- Review question (constitution §13): no ranking, scoring, or summarising of legal authority. The UPL disclaimer's `contentinfo` landmark is *strengthened* — it is now the page's only one.
- Who is the stronger here? The static export is the surface a prospective law student reaches first, with no account and no onboarding. Holding it to a weaker standard than the logged-in platform inverts who gets the careful work.

## 3. Goals

- G1: One set of UI primitives, physically shared, with drift impossible.
- G2: The static site meets the same universal rules as the platform.
- G3: The section clock stays visible during a drill, where the viewport can afford it.
- G4: `ux_audit.py` covers both front ends and both languages they are written in.

## 4. Non-Goals

- NG1: Porting `lsat-static`'s `QuestionCard` onto `frontend/lib/shell/rovingFocus.ts` (BL-20260831-08). Its hand-rolled implementation is correct and is now gated by R10; cross-app TS imports are a separate problem from cross-app CSS.
- NG2: Giving the static site the platform's shell — it has no rail, sidebar, or inspector and should not.
- NG3: Tailwind, or any build step, in the static export (spec 039 NFR-PERF-1).
- NG4: A dockable timer on the static site; there is nowhere to dock it.
- NG5: Unifying the two timer implementations (BL-20260830-04).

## 5. User Stories

- As a keyboard user landing on the published site, I want to skip the header and reach the questions in one keystroke.
- As a screen-reader user, I want one footer landmark, so "navigate to contentinfo" lands on the disclaimer that matters.
- As a student mid-drill on a laptop, I want the section clock pinned while I read, the way it now is on the platform.
- As a student on a phone, I do *not* want a third of the screen spent on pinned chrome.
- As a contributor, I want a change to the shared focus ring or z-scale to reach both apps, and to be told when the copies drift.

## 6. Functional Requirements

- **FR-1**: `frontend/ui/base.css` holds the cross-product primitives — the z-scale, the focus-ring tokens and classes, and the reduced-motion opt-out. `layout.css` imports it and keeps only shell-specific metrics and the scroll classes.
- **FR-2**: The static site consumes those primitives. Next refuses to resolve a CSS `@import` outside an app root (verified: Turbopack "Module not found"), so the file is mirrored byte-for-byte at `lsat-static/app/base.css`, synced by `make ui-sync`.
- **FR-3**: `ux_audit.py` R12 fails the build when the two copies differ. A mirror nobody checks is a fork with extra steps.
- **FR-4**: The static site has a skip link, visible on focus, as the first tab stop, targeting the existing `main#view`.
- **FR-5**: The static site declares exactly one `contentinfo` landmark: the UPL disclaimer. The page's information strip becomes a plain element.
- **FR-6**: The static site's `z-index` and sticky offsets come from tokens: `--z-sticky-header` for the site header, `--z-sticky-sub` for the drill head, and a measured `--site-header-h` / `--drill-head-h` for the sticky stack.
- **FR-7**: On viewports at or above the two-column breakpoint (820px), the drill head — which carries the section clock — pins beneath the site header, and the passage column pins beneath both with `align-self: start` so sticky has somewhere to travel. Below that breakpoint only the site header pins.
- **FR-8**: `ux_audit.py` audits both front ends, applying the universal rules (R3–R6, R9–R11) to each and the shell rules (R1, R2, R7, R8) to the platform only.
- **FR-9**: `ux_audit.py` reads stylesheets as well as `.tsx`, so R4 and R9 apply to a site that writes its layout in CSS.

## 7. Non-Functional Requirements

- **NFR-PERF-1**: The static export remains Tailwind-free and small. Verified on the built artifact: no `tailwind` or `--tw-` token in the emitted CSS, 9.6 KB total.
- **NFR-A11Y-1**: The static site keeps its *global* `:focus-visible` rule rather than adopting the platform's opt-in `.focus-ring` class — global coverage is stronger, and it is why this site was the reference implementation. Only the colour moves to the shared token.
- **NFR-A11Y-2**: Pinned chrome must not dominate a small viewport. At 390px the header alone pins (16% of the viewport); pinning the drill head too would have cost 37%.
- **NFR-TEST-1**: R3 and R11 must not fire on correct static-site markup. Both had false-positive classes that only appeared on a second surface, and both were corrected rather than worked around.
- **NFR-SEC-1**: No new dependencies in either app.
- **NFR-DOCS-1**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, and `frontend/ui/README.md` describe one contract covering both front ends.

## 8. Data Model Impact

None.

## 9. API Surface

None.

## 10. Agent / Crew Impact

None to `agents_runtime`.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given the published static site, the skip link is the first tab stop, is off-screen until focused, and targets `main#view`.
- **AC-2**: Given the built `out/index.html`, there is exactly one `<main>` and exactly one `contentinfo`.
- **AC-3**: Given a drill at 1440px scrolled 776px, the site header sits at 0 and the drill head pins directly beneath it with no gap (measured −1px tuck), leaving the section clock visible.
- **AC-4**: Given the same drill at 390px, neither the drill head nor the passage is sticky, and the pinned header is at most a fifth of the viewport.
- **AC-5**: Given `frontend/ui/base.css` and its mirror, `ux_audit.py` exits 0 when identical and reports R12 when they differ.
- **AC-6**: Given the reverted static markup and CSS, the audit reports R3 (no `<main>`), R11 (placeholder-only control), R4 (literal z-index) and R9 (magic sticky offset); on the fixed tree it exits 0.
- **AC-7**: Given the built export, the emitted CSS contains the shared tokens and no Tailwind runtime.
- **AC-8**: `make test-frontend`, `tsc --noEmit`, `npm run build` (both apps), and `make lint-specs` are clean.

## 13. Risks & Open Questions

- **R-1**: A mirrored file is duplication. Accepted because Next cannot resolve the cross-app import and R12 makes divergence a build failure; `make ui-sync` is the one-command fix named in the failure message.
- **R-2**: `--site-header-h` and `--drill-head-h` are measured constants and would desynchronise if the header's content changed height. Mitigated by keeping the stack to the wide-viewport case where the header is a single row, and by erring a pixel under so the failure mode is an invisible tuck rather than a visible gap.
- **R-3**: A passage taller than the viewport gets no benefit from top-stickiness — browsers only pin such an element once its bottom is reached. Recorded as a follow-up; the previous code had the same limitation *plus* the `align-self` bug that disabled it entirely.
- **R-4**: Extending the audit to a second surface surfaced two false-positive classes in existing rules. Both were fixed, but it is evidence that a rule proven on one codebase is not proven in general.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG.
