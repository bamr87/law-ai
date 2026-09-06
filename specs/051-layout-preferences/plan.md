# Plan: Layout preferences

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: make every layout choice an ordinary setting, then the shell is a plain composition over settings and the menu is a view of the same rows.

## 1. Architecture

### The settings store is the preference layer

Spec 043 already put one layout choice — the timer's dock — in the instance-scoped settings store and read it live through `useSetting`. Every preference here follows the same path, which buys three things for the price of a catalog entry each: persistence across navigations and reloads, a labelled control on `/settings` with inheritance provenance, and a live read anywhere on the page (`useSyncExternalStore`, so no mount effects and no hydration mismatch).

`useSetting` gains a third tuple element, the `Effective` row, because the shell needs to tell "the user chose closed" from "nothing is stored": a stored inspector choice wins over the UPL-route auto-open, an absent one does not.

### Where a panel renders

```
ui.sidebar.side   ─┐
ui.inspector.side ─┴─→ resolvePanelSides() ─→ { left: PanelKey[], right: PanelKey[] }
```

Pure, so the ordering rule is unit-tested without a DOM: the sidebar is always outermost and the inspector always innermost, whichever edge each is on. `AppShell` maps the result on either side of `<main>`; a `DockedPanel` takes the edge only to pick its border, and keeps its width and its breakpoint whichever edge it moves to. The compact drawers take the same edge.

### One menu, three mirrors

```
LayoutMenu (masthead)  ─┐
/settings              ─┼─→ settings store ─→ useSetting() ─→ AppShell, Masthead, PageLayout,
⌘K palette actions     ─┘                                     SectionTimerWidget, LsatLibrary
```

The menu is a `role="menu"` of `menuitemcheckbox` and `menuitemradio` rows over the same settings. The two panel rows are the exception: they reflect the *effective* open state (URL first, preference second) and toggle through the shell's own handler, so the row, the masthead button, and the `[` / `]` keys can never disagree.

### Files

```
frontend/lib/settings/catalog.ts            EDIT  eleven layout settings; grouped catalog order
frontend/lib/shell/layout.ts                NEW   LAYOUT_SETTINGS, resetLayout, resolvePanelSides
frontend/lib/shell/panels.ts                EDIT  withoutPanels (the URL half of a reset)
frontend/lib/shell/commands.ts              EDIT  toggle-rail, toggle-breadcrumbs, reset-layout
frontend/components/shell/useSetting.ts     EDIT  exposes the Effective row
frontend/components/shell/LayoutMenu.tsx    NEW   the menu
frontend/components/shell/AppShell.tsx      EDIT  reads the preferences; maps the arrangement
frontend/components/shell/Masthead.tsx      EDIT  breadcrumb / scope toggles; menu slot
frontend/components/shell/PageLayout.tsx    EDIT  ui.page_header
frontend/components/shell/SettingsForm.tsx  EDIT  one heading per key prefix
frontend/components/lsat/SectionTimerWidget.tsx
                                            EDIT  lsat.timer.visible; "Show when idle" row
frontend/components/LsatLibrary.tsx         EDIT  lsat.library.contents / outline; grid table
```

## 2. Decisions worth recording

- **A menu, not drag handles.** Same reasoning as spec 043 NG1: keyboard-operable by construction, and every state is announced. Drag would need a parallel keyboard path for a handful of binary choices.
- **Reset deletes rows rather than writing defaults.** A deleted row reads as "inherited" on `/settings`, which is the truth. A written default would look like a choice the user made, and would shadow a future org-scope value once spec 036 lands.
- **Panel toggles write the URL *and* the preference.** Spec 041 made the URL the source of truth so a layout is linkable and Back restores it; that stays. The preference is the fallback for a URL that says nothing — which is every URL a user reaches by clicking a link. Without it, a collapse is undone by the next navigation.
- **A stored inspector choice beats the UPL auto-open.** The auto-open exists to put the disclaimer on screen, and the footer disclaimer inside `<main>` does that on every route regardless. With nothing stored the auto-open still applies, so a fresh profile behaves as spec 040 specified.
- **Defaults equal the old layout.** Every preference's default is what the shell did before; a fresh profile cannot tell this spec shipped.
- **Module rows by route prefix.** `LayoutMenu` shows the timer row on `/lsat*` and the library rows on `/lsat/library*`. That is a route name in the shell, which spec 040 avoided; it is bounded to one component and recorded as a follow-up (a module-declared registry).

## 3. Data & Schema Migrations

None. Browser storage only, in the existing `law-ai.settings.v1` key; unknown or stale values fall back to the defaults through each setting's `parse`.

## 4. Provenance & Audit Hook-up

Nothing to hook up: no model, tool, or graph call is made or changed.

## 5. HITL Gates

None. `human_approval_required` is false for every path this spec touches.

## 6. Test Strategy

- Pure logic: `__tests__/lib/shellLogic.test.ts` — `resolvePanelSides` for all four edge combinations, `resetLayout` deleting only layout rows, `withoutPanels`, the palette's new actions.
- The menu: `__tests__/shell/LayoutMenu.test.tsx` — roles and names, a toggle writing the store and keeping the menu open, a radio moving a panel, panel rows routed through the shell, module rows only on their routes, roving focus and Escape, Reset closing.
- The shell: `__tests__/shell/AppShell.test.tsx` — rail hidden with the tab bar kept, the sidebar docked right and outermost, a toggle recorded as the preference, a stored choice beating the UPL auto-open and the URL beating both. `__tests__/shell/ShellBehaviour.test.tsx` — the breadcrumb trail hidden with the home link kept, the rail toggled from the palette, the compact header mode.
- Widgets: `__tests__/shell/lsatTimerDock.test.tsx` — an idle clock hidden, a running one never; the "Show when idle" row. `__tests__/components/lsat/LsatLibrary.test.tsx` — both side columns dropped, the contents still reachable through the disclosure.
- Visual: Playwright captures under `docs/images/` of the menu, a moved-and-hidden arrangement, and the grouped settings page.

## 7. Rollout

Ships with the frontend; no flag. Defaults reproduce the previous layout, so nothing changes for anyone who does not open the menu.

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| A hidden rail strands a mouse user | low | med | Palette button and Layout menu cannot be hidden; a rail-hidden "Modules" menu is a follow-up |
| Post-hydration reflow for non-default layouts | high | low | Same trade as spec 043; cookie-backed server read is a follow-up |
| Both panels on one edge crowd a 1024px screen | low | low | Each panel keeps its own breakpoint (`md` / `lg`), so the inspector column still yields first |
| A stale enum value in storage | low | low | `parseEnum` falls back to the default |

## 9. Estimated Effort

One agent session. No human pairing needed; the UPL rule (footer never hideable) was the only judgement call and it is written into the catalog comment.
