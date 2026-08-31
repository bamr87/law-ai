# Plan: Application shell navigation & scroll contract

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: rework the spec 040 shell in place; add a layout token layer and a page frame; make the contract machine-checkable.

## 1. Architecture

### The load-bearing decision

The document stops scrolling. `AppShell` becomes `h-dvh overflow-hidden` with `<body>` matching, so the chrome is a set of flex children of a viewport-height row rather than sticky elements inside a scrolling page. `position: sticky` survives normal scrolling but not overscroll and depends on the document scrolling at all; a flex child of a fixed-height row cannot move regardless.

The cost is that `window.scrollY` is permanently 0. `ShellScroll` absorbs it: `useMainScrollController` owns the `<main>` ref, tracks the offset, and publishes `{ scrolled, scrollTop, scrollToTop, mainRef }` through context. `PageLayout` and `BackToTop` read it. Audit rule R2 stops a screen from re-introducing its own viewport-sized scroller.

`h-dvh`, not `h-screen`: on mobile Safari/Chrome `100vh` is the *expanded* viewport, so a `h-screen` shell parks its bottom tab bar behind the browser's own chrome.

### The sticky stack

One number, three rungs. `--shell-pageheader-h` is the condensed page-header height; `.shell-sticky-sub` parks at it, `.shell-sticky-aside` parks below it plus `--shell-toolbar-h`. Nothing hard-codes an offset, so a header height change moves every sticky element with it. `scroll-padding-top` on `.shell-scroll` keeps anchor targets out from under the header.

### Responsive panels

Docked column vs off-canvas drawer is a *markup* difference, not a styling one, so it needs JS: `useMediaQuery` starts `false` (no viewport on the server, so no hydration mismatch) and updates after mount. Panels stay URL state (`?sidebar=0`), which keeps a layout linkable and restorable by Back; the media query only changes the *default* when the URL is silent, so a shared link still opens what it promised.

### Files

```
frontend/ui/layout.css              NEW  tokens: metrics, sticky stack, z-scale, scroll, focus, motion
frontend/ui/README.md               NEW  catalog
frontend/lib/shell/panels.ts        NEW  URL panel state (pure)
frontend/lib/shell/shortcuts.ts     NEW  keyboard contract (pure)
frontend/lib/shell/scrollMemory.ts  NEW  per-route offsets (pure, sessionStorage)
frontend/lib/shell/commands.ts      NEW  palette model (pure)
frontend/lib/modules/catalog.ts     EDIT breadcrumbsForPath()
frontend/components/shell/
  AppShell.tsx                      EDIT viewport lock, drawers, shortcuts, overlays
  Masthead.tsx                      EDIT breadcrumbs, aria-controls, palette trigger
  NavRail.tsx                       EDIT full-height, own scroll, non-colour active marker
  ContextSidebar.tsx                EDIT own scroll
  InspectorPanel.tsx                EDIT own scroll
  PageLayout.tsx                    NEW  page frame + StickyToolbar
  ShellScroll.tsx                   NEW  scroll context + controller
  Overlay.tsx                       NEW  useFocusTrap, Scrim, Drawer
  CommandPalette.tsx                NEW
  ShortcutsHelp.tsx                 NEW
  MobileTabBar.tsx                  NEW
  BackToTop.tsx                     NEW
  useMediaQuery.ts                  NEW
frontend/app/layout.tsx             EDIT document overflow, viewport, footer moves into the shell
frontend/app/(app)/*/page.tsx       EDIT onto PageLayout; drop nested <main>
frontend/app/(app)/loading.tsx      NEW
frontend/app/(app)/error.tsx        NEW
frontend/app/not-found.tsx          NEW
frontend/components/{LsatLab,AgentDashboard,KnowledgeGraph,AnalysisStudio}.tsx
                                    EDIT sticky toolbars, panel scroll classes, focus rings
frontend/.prettierrc                NEW  pins the house style prettier had no config for
scripts/ux_audit.py                 NEW  R1-R9
Makefile / .github/workflows/ci.yml EDIT ux-audit target + gate
docs/ui-ux-review.md                NEW  rubric + pass log
.claude/{skills/ux-review,commands/ux-review.md}
                                    NEW  the loop
```

## 2. Why this shape

- **Pure logic split out of components.** `panels`, `shortcuts`, `scrollMemory`, `commands` are plain functions, so the rules that matter — "a bare key never fires while typing", "a 0 offset is deleted, not stored" — are unit-testable without mounting a shell, and every surface agrees on them.
- **`PageLayout`, not `PageHeader` + `PageBody`.** Two components would mean two places to state the same width, and the third route to get it wrong would not be noticed. One component per page is also what makes audit rule R7 expressible.
- **Palette generated from the catalog.** A hand-listed palette is a second registry that silently goes stale. `buildCommands(MODULE_CATALOG)` means registering a module is the only edit.
- **The audit is stdlib and static.** It joins `spec_validator.py` and `backlog_lint.py` in CI's Spec Drift Gate — no container, no `node_modules`, runs in seconds on every PR.

## 3. Test strategy

| Layer | Covers |
|-------|--------|
| `__tests__/lib/shellLogic.test.ts` | panel resolution, keyboard matching (incl. the typing guard), scroll memory (incl. corrupt storage), palette ranking, breadcrumbs |
| `__tests__/shell/ShellBehaviour.test.tsx` | viewport lock, chrome outside `<main>`, footer inside it, scroll restoration, shortcuts end to end, breadcrumb trail, `aria-controls`, header condensing, palette navigation/actions/empty state, help sheet |
| `__tests__/shell/AppShell.test.tsx` (existing) | spec 040 panel/URL behaviour — kept passing unchanged as the regression guard |
| `scripts/ux_audit.py` | the nine structural rules, on every file, forever |

jsdom cannot lay out `position: sticky`, so the component tests assert the *contract* — class names, `data-condensed`, DOM ancestry — and the class-to-behaviour mapping lives in one reviewable CSS file. Real-layout coverage is a recorded follow-up.

## 4. Rollout

Single PR. No migration, no flag: URLs, panel query params, and the module catalog API are unchanged, so spec 040's tests pass untouched.

## 5. Risks

Carried from [spec.md](spec.md) §13. The one worth restating: a static audit is only worth its false-positive rate, so every rule was verified by injecting a violation and confirming it fails, and file-level exemptions must carry a written reason.
