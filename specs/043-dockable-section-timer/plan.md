# Plan: Dockable LSAT section timer

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: make the clock a store first, then docking is a rendering decision rather than a state-migration problem.

## 1. Architecture

### Why the store comes first

`app/(app)/@sidebar` is a parallel-route slot: the sidebar and the page are sibling subtrees, not parent and child. A timer holding `remaining` in `useState` cannot move between them — React would unmount one instance and mount another, and a student would watch a running section snap back to 35:00.

So `lib/lsat/timerStore.ts` owns the clock and every dock renders a *view* of it. That also fixes a latent bug the single-mount design hid: two mounted timers previously ran two independent clocks, and one interval now serves the app.

Deadline-based rather than tick-accumulating, because browsers throttle intervals in background tabs — the exact situation a student creates by opening a case in another module mid-section.

### Where a widget renders

```
preference (lsat.timer.dock)  ─┐
open panels (sidebar/inspector)├─→ resolveDock() ─→ Dock | null
on its own route?             ─┘
```

`resolveDock` is a pure function so the fallback rules are testable without a DOM. The rule that matters: **a collapsed panel must never hide a running clock**, so an unavailable preference degrades to an open zone instead of to nothing.

Route policy lives in the widget, not the zone: `DockZone` maps a registry and each widget decides whether it belongs here and now. That is what keeps `AppShell` from learning what LSAT is.

### Files

```
frontend/lib/lsat/timerStore.ts             NEW  the clock + sessionStorage durability
frontend/lib/shell/docks.ts                 NEW  resolveDock (pure)
frontend/components/lsat/SectionTimerWidget.tsx
                                            NEW  the view + Move menu + route policy
frontend/components/shell/DockZone.tsx      NEW  registry -> zone
frontend/components/shell/useSetting.ts     NEW  live single-setting read
frontend/components/shell/AppShell.tsx      EDIT dock zones in both panels and both drawers
frontend/components/LsatLab.tsx             EDIT inline zone; attempts feed the store
frontend/components/shell/SettingField.tsx  EDIT enum select control
frontend/components/shell/SettingsForm.tsx  EDIT useSyncExternalStore (fixes hydration)
frontend/lib/scope/{types,store}.ts         EDIT options on SettingDefinition; subscribable store
frontend/lib/settings/{define,catalog}.ts   EDIT parseEnum; lsat.timer.dock
frontend/ui/layout.css                      EDIT --z-popover rung
```

## 2. Decisions worth recording

- **A menu, not drag-and-drop.** Menus are keyboard-operable by construction. Drag would need a parallel keyboard path to stay accessible, for a three-target choice.
- **sessionStorage for the clock, localStorage for the preference.** A half-spent section waiting for you tomorrow would be worse than starting fresh; a dock preference tomorrow is exactly right.
- **The deadline is persisted, not the remaining seconds.** Time spent reloading counts against a running section, which is what a proctored clock does.
- **`useSyncExternalStore` everywhere the settings store is read.** It renders the server snapshot through hydration, which is what fixes the `/settings` mismatch, and subscribing makes the widget menu and the settings page agree instantly.

## 3. Test strategy

| Layer | Covers |
|-------|--------|
| `__tests__/shell/lsatTimerDock.test.tsx` | `resolveDock` fallbacks incl. the collapsed-panel and nowhere-to-put-it cases; deadline arithmetic under fake timers; pause holds; pace accumulation; sessionStorage shape; default dock; move via the menu; **clock survives a move**; off-route visibility gated on progress |
| `__tests__/lib/modules.test.ts` | The setting catalog grew deliberately; every enum's options round-trip through its own parser |
| `__tests__/components/LsatLab.test.tsx` | Updated: the page no longer owns the timer, and pace is asserted on the store |
| Real browser | Docking, the move menu, client-side navigation, and reload durability — none of which jsdom can prove |

## 4. Rollout

One commit on the spec 041/042 branch; it builds on `frontend/ui/` and the settings store from those specs.

## 5. Risks

Carried from [spec.md](spec.md) §13. The honest one: an MSW-backed LsatLab assertion failed once mid-implementation and passed on three subsequent full runs. It is not timer-related and is recorded as a follow-up rather than declared fixed.
