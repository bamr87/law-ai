import { INSTANCE_SCOPE, userScopeFor } from '@/lib/scope/instance'
import { deleteSettingValue, serverSyncScope } from '@/lib/scope/store'
import type { SettingDefinition } from '@/lib/scope/types'
import {
  backToTopVisible,
  breadcrumbsVisible,
  inspectorDefaultOpen,
  inspectorSide,
  libraryContents,
  libraryOutline,
  lsatTimerDock,
  lsatTimerVisible,
  pageHeaderMode,
  railExpanded,
  railVisible,
  scopeSwitcherVisible,
  sidebarDefaultOpen,
  sidebarSide,
  type PanelSide,
} from '@/lib/settings/catalog'
import type { PanelKey } from './panels'

/**
 * Layout preferences (spec 051): what the shell shows and where.
 *
 * The model is deliberately small. Every preference is an ordinary setting in
 * the instance-scoped store, so it persists like the timer dock does, shows
 * up on `/settings` for free, and can be reset as a group. What lives here is
 * the pure logic the shell and its menu share — nothing that needs a DOM.
 */

/**
 * Every setting the Layout menu owns and "Reset layout" clears.
 *
 * The boundary is "does it change the shape of the shell", not "is it a
 * preference" — which is the question BL-20260905-33 asked about
 * `lsat.timer.duration`. A drill length describes the *exercise*, not the
 * screen: a student who set a 10-minute homework clock and then tidied their
 * layout has said nothing about how long they want to drill, and having Reset
 * layout put them back on a 35-minute section would be this button inventing
 * an answer. It stays out, and it is not left without a way back either — the
 * timer's own Length menu is one click from "35 min — full section" whenever
 * the clock is on screen, and `/settings` gives it the same per-field "Reset
 * to inherited" every catalog setting has.
 *
 * The mirrored-cookie contract reads this list too: `MIRRORED_SETTING_KEYS` in
 * `lib/scope/rows.ts` carries exactly these keys, and a test fails if the two
 * drift (BL-20260905-29).
 */
export const LAYOUT_SETTINGS: SettingDefinition<unknown>[] = [
  railVisible as SettingDefinition<unknown>,
  railExpanded as SettingDefinition<unknown>,
  sidebarDefaultOpen as SettingDefinition<unknown>,
  sidebarSide as SettingDefinition<unknown>,
  inspectorDefaultOpen as SettingDefinition<unknown>,
  inspectorSide as SettingDefinition<unknown>,
  breadcrumbsVisible as SettingDefinition<unknown>,
  scopeSwitcherVisible as SettingDefinition<unknown>,
  backToTopVisible as SettingDefinition<unknown>,
  pageHeaderMode as SettingDefinition<unknown>,
  lsatTimerDock as SettingDefinition<unknown>,
  lsatTimerVisible as SettingDefinition<unknown>,
  libraryContents as SettingDefinition<unknown>,
  libraryOutline as SettingDefinition<unknown>,
]

/**
 * Back to the defaults — by deleting the rows, not by writing the defaults.
 * A deleted row reads as "inherited" on `/settings`, which is the truth; a
 * written default would look like a choice the user made.
 */
export function resetLayout(): void {
  // BL-20260905-10: reset means "back to what I inherit", so a signed-in user
  // drops their own rows and lands on the instance default an admin seeded —
  // deleting the instance rows from here would reset the *instance* for
  // everyone, which is not what a personal Reset button may do. Signed out,
  // the instance rows are the only ones there are and behaviour is unchanged.
  const user = userScopeFor(serverSyncScope())
  for (const def of LAYOUT_SETTINGS) {
    deleteSettingValue(user ? user.id : INSTANCE_SCOPE.id, def.key)
  }
}

export interface PanelArrangement {
  /** Outermost first — rendered left to right after the rail. */
  left: PanelKey[]
  /** Innermost first — rendered left to right after the main region. */
  right: PanelKey[]
}

/**
 * Which panels dock on which edge.
 *
 * Both panels may sit on the same edge. The sidebar is always the outer one
 * and the inspector always the inner one, on either side: the sidebar is
 * navigation, which belongs at the edge of the screen, and the inspector is
 * about the page, which belongs beside it. Returning arrays in render order
 * keeps `AppShell` a plain map over the result.
 */
export function resolvePanelSides(sides: {
  sidebar: PanelSide
  inspector: PanelSide
}): PanelArrangement {
  const left: PanelKey[] = []
  const right: PanelKey[] = []
  if (sides.sidebar === 'left') left.push('sidebar')
  if (sides.inspector === 'left') left.push('inspector')
  if (sides.inspector === 'right') right.push('inspector')
  if (sides.sidebar === 'right') right.push('sidebar')
  return { left, right }
}
