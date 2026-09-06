# `frontend/ui/` — the first-party design system

Two halves, landing in two specs:

| Half | File | Spec | Status |
|------|------|------|--------|
| **Layout & scroll** — shell metrics, the z-index scale, scroll and focus primitives | [layout.css](layout.css) | 041 | shipped |
| **Palette & components** — colour tokens, semantic classes, React primitives | `tokens.css`, `semantic.css`, `components/` | [039](../../specs/039-design-system/spec.md) | planned |

Do not add colours to `layout.css` beyond the two scrollbar hooks and the two focus-ring hooks already there; those exist so spec 039 can re-point them at real palette tokens in one edit. `layout.css` is imported by [`app/globals.css`](../app/globals.css) and is the only place any of these values are defined.

## Sharing with the static site

`base.css` holds the primitives both front ends need — the z-scale, the focus ring, the motion opt-out. `layout.css` imports it; `lsat-static` cannot, because Next refuses to resolve a CSS `@import` outside an app's own root (Turbopack: "Module not found"). So it is **mirrored** to `lsat-static/app/base.css`:

- Edit `frontend/ui/base.css`, never the mirror.
- Run `make ui-sync`.
- `scripts/ux_audit.py` R12 fails the build if the two ever differ.

Keep `base.css` plain CSS — no `@apply`, no `@theme`, no utilities. The static export is Tailwind-free (spec 039 NFR-PERF-1) and anything needing a build step would break it. Shell metrics and `.shell-*` classes stay in `layout.css`, because a site with no shell should not inherit tokens describing one.

The same rule now covers behaviour, not just styling. Every mirrored file is listed in `SHARED_MIRRORS` in `scripts/ux_audit.py`, and R12 byte-compares each pair:

| Source (edit this) | Mirror | Shares |
|--------------------|--------|--------|
| `frontend/ui/base.css` | `lsat-static/app/base.css` | z-scale, focus ring, motion opt-out |
| `frontend/lib/shell/rovingFocus.ts` | `lsat-static/lib/rovingFocus.ts` | what an arrow key does in a composite widget (BL-20260831-08) |
| `frontend/lib/lsatTimer.ts` | `lsat-static/lib/lsatTimer.ts` | clock formatting and pace arithmetic |
| `frontend/lib/lsat/timerStore.ts` | `lsat-static/lib/lsat/timerStore.ts` | the section-clock state machine both timers view (BL-20260830-04) |

A mirrored module has to compile in **both** roots, which constrains what it may import: only `@/lib/…` paths that exist on both sides, and no Tailwind, no settings catalog, no API client. That is why the platform's `SectionTimerWidget` and the static `SectionTimer` are separate files — the store is shared, the markup is not, because docking and Tailwind exist on only one side.

## Tokens

### Shell metrics

`--shell-masthead-h`, `--shell-rail-w`, `--shell-sidebar-w`, `--shell-inspector-w`, `--shell-tabbar-h`. Chrome that never scrolls. Read them with `calc()` when a screen needs to size itself against the shell — for example `max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-3rem)]` — instead of copying the same number into five files.

### The sticky stack

`--shell-pageheader-h` is the condensed height of a `PageLayout` header; `--shell-toolbar-h` is the height of a `StickyToolbar`. Everything that pins itself parks against these, so changing a header height moves every sticky element with it. Three rungs, top to bottom:

| Class | Parks at | For |
|-------|----------|-----|
| `.shell-sticky-header` | `0` | The page header. `PageLayout` applies it; you should not. |
| `.shell-sticky-sub` | `--shell-pageheader-h` | Toolbars, tab bars, filter rows. Use `StickyToolbar`. |
| `.shell-sticky-aside` | header + toolbar | A column that must stay beside its content — the RC passage next to its questions. |

A page with no sticky header sets `--shell-pageheader-h: 0px` on its own root.

**The gotcha that will cost you an hour:** a sticky element that is a grid or flex *item* defaults to `align-self: stretch`, which makes it exactly as tall as its row — leaving `position: sticky` no distance to travel, so it silently does nothing. Add `self-start`. The Knowledge Graph case picker is the worked example.

### The z-scale

`--z-content` `0` · `--z-sticky-sub` `20` · `--z-sticky-header` `30` · `--z-popover` `35` · `--z-masthead` `40` · `--z-scrim` `50` · `--z-drawer` `60` · `--z-palette` `70`.

Never hand-write a z-index. `scripts/ux_audit.py` R4 fails the build on a literal, because a literal has no idea the drawer sits at 60.

## Classes

| Class | Use |
|-------|-----|
| `.shell-scroll` | The single page-content scroller. `AppShell` puts it on `<main>`; nothing else should use it. |
| `.shell-panel-scroll` | Any panel or list that scrolls independently — nav rail, sidebar, inspector, a bounded list inside a card. Contains overscroll so a flick at the end of the list does not chain into the page. |
| `.focus-ring` | The app-wide `:focus-visible` indicator. Put it on every interactive element. |
| `.focus-ring-practice` | Same, in LSAT amber, for practice-context controls. |
| `.shell-motion` | Opts an element's transitions out under `prefers-reduced-motion: reduce`. |

`.shell-panel-scroll` clips horizontally on purpose. A `<pre>` that needs sideways scroll keeps its own `overflow-auto` — R1 exempts `<pre>` for exactly this.

## Components

Under [`../components/shell/`](../components/shell/) until spec 039 gives `frontend/ui/components/` a home:

| Component | Use |
|-----------|-----|
| `PageLayout` | The frame for every route: sticky condensing header + measured body container. Pick a `width` (`wide`/`roomy`/`regular`/`narrow`) and an `accent`; never hand-roll `mx-auto max-w-*`. |
| `StickyToolbar` | A control bar pinned under the page header. Pass `label` when it is a real region. |
| `Drawer` (`Overlay.tsx`) | Off-canvas panel for compact viewports. Focus-trapped, Escape-dismissed, focus restored. |
| `useFocusTrap` | The same behaviour for any new overlay. Use it rather than writing a fourth focus trap. |
| `useShellScroll` | Read the main region's scroll offset. `window.scrollY` is always 0 — the shell locks the viewport. |
| `useMediaQuery` | Only for layout decisions that change *markup* (docked column vs drawer). Everything else is a CSS breakpoint. |
| `DockZone` / `resolveDock` | Persistent module widgets that live in the shell's chrome. A zone renders every registered widget; each widget decides whether it belongs in the asking dock and on the current route, so `AppShell` never learns what a module is. `resolveDock` honours the user's preference and falls back to an open zone rather than hiding the widget when a panel is collapsed. |
| `LayoutMenu` / `lib/shell/layout.ts` | Layout preferences (spec 051). The menu is a `role="menu"` over the `ui.*` settings — show/hide rows, an edge per side panel, the page-header mode, Reset. `resolvePanelSides` is the pure ordering rule (sidebar outermost, inspector innermost) that `AppShell` maps; `LAYOUT_SETTINGS` is the list Reset clears. A new preference is one catalog entry plus one row here; the UPL footer must never get one. |
| `useSetting` | Read one setting, live. `useSyncExternalStore` over the settings store — safe through hydration and reactive when the value changes anywhere on the page. Never read `listSettingValues()` during render. |
| `useRovingTabIndex` | Any composite widget — tab bar, radiogroup, listbox, toolbar. Makes the group **one** tab stop with arrow-key movement inside it, selection following focus. Never hand-roll this: `ux_audit.py` R10 checks the ARIA attributes and `__tests__/shell/rovingFocus.test.tsx` checks the behaviour. |

## Adding a surface

Register it in [`../lib/modules/catalog.ts`](../lib/modules/catalog.ts). That one edit gives it nav rail placement, compact tab bar placement, breadcrumbs, a contextual sidebar, inspector copy, and a ⌘K palette entry. `AppShell.tsx` must never learn a route name.
