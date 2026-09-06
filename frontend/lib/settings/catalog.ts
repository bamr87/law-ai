import {
  defineSetting,
  INSTANCE_ONLY,
  parseBoolean,
  parseEnum,
  parseNumber,
} from './define'
import type { SettingDefinition } from '@/lib/scope/types'

export const hitlThreshold = defineSetting({
  key: 'analysis.hitl_threshold',
  label: 'HITL confidence threshold',
  help: 'Analysis below this confidence (0–1) is flagged for human review. Displayed as a process gate, not a measure of legal correctness.',
  default: 0.7,
  settableAt: INSTANCE_ONLY,
  lockable: true,
  parse: parseNumber,
})

export const showCitationCounts = defineSetting({
  key: 'graph.show_citation_counts',
  label: 'Show citation counts on the graph',
  help: 'Citation counts measure litigation frequency and repeat-player resources, not legal correctness (constitution §13). When shown, the graph legend must say so.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: true,
  parse: parseBoolean,
})

export const inspectorDefaultOpen = defineSetting({
  key: 'ui.inspector.default_open',
  label: 'Open inspector by default',
  help: 'When no `inspector` query param is set, open the inspector. Collapsing or expanding it from the masthead records the choice here too, so a layout survives a navigation. A stored value wins over the UPL-route auto-open; with none stored, a UPL route still opens it.',
  default: false,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

/** Where a dockable widget sits. `inline` means in the module's own page. */
export const DOCKS = ['sidebar', 'inspector', 'inline'] as const
export type Dock = (typeof DOCKS)[number]

export const lsatTimerDock = defineSetting<Dock>({
  key: 'lsat.timer.dock',
  label: 'LSAT timer dock',
  help: 'Where the section timer sits. It stays out of the way in a side panel by default, and follows you to other modules while a section is in progress so the clock is never hidden behind a navigation.',
  default: 'sidebar',
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseEnum(DOCKS),
  options: [
    { value: 'sidebar', label: 'Sidebar' },
    { value: 'inspector', label: 'Inspector' },
    { value: 'inline', label: 'In page' },
  ],
})

/**
 * Layout preferences (spec 051). Every one of these is owned by the masthead's
 * Layout menu and by "Reset layout"; `/settings` renders them under one
 * heading. They describe what the shell *shows*, never what it *does* — the
 * UPL disclaimer footer has no setting on purpose.
 */

export const railVisible = defineSetting({
  key: 'ui.rail.visible',
  label: 'Show the navigation rail',
  help: 'The module rail down the left edge. With it hidden every module is still one ⌘K away, and the compact tab bar below `md` is unaffected.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const sidebarDefaultOpen = defineSetting({
  key: 'ui.sidebar.default_open',
  label: 'Open sidebar by default',
  help: 'When no `sidebar` query param is set, open the contextual sidebar. Collapsing or expanding it from the masthead records the choice here too, so a layout survives a navigation.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

/** Which edge of the shell a side panel docks to. */
export const PANEL_SIDES = ['left', 'right'] as const
export type PanelSide = (typeof PANEL_SIDES)[number]

const SIDE_OPTIONS: { value: PanelSide; label: string }[] = [
  { value: 'left', label: 'Left' },
  { value: 'right', label: 'Right' },
]

export const sidebarSide = defineSetting<PanelSide>({
  key: 'ui.sidebar.side',
  label: 'Sidebar position',
  help: 'Which edge the contextual sidebar docks to. Both panels may share an edge; the sidebar is always the outer one.',
  default: 'left',
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseEnum(PANEL_SIDES),
  options: SIDE_OPTIONS,
})

export const inspectorSide = defineSetting<PanelSide>({
  key: 'ui.inspector.side',
  label: 'Inspector position',
  help: 'Which edge the inspector docks to. Both panels may share an edge; the inspector is always the inner one, next to the page.',
  default: 'right',
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseEnum(PANEL_SIDES),
  options: SIDE_OPTIONS,
})

export const breadcrumbsVisible = defineSetting({
  key: 'ui.masthead.breadcrumbs',
  label: 'Show the breadcrumb trail',
  help: 'The "where am I" trail in the masthead. It is hidden below `md` regardless, where the compact tab bar names the section.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const scopeSwitcherVisible = defineSetting({
  key: 'ui.masthead.scope_switcher',
  label: 'Show the scope switcher',
  help: 'The scope chip in the masthead. Only the instance scope is live (spec 036 NG3), so until user accounts land it is a label rather than a control.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const backToTopVisible = defineSetting({
  key: 'ui.back_to_top',
  label: 'Show the back-to-top button',
  help: 'The floating ↑ Top button that appears once the page has scrolled. The palette\'s "Scroll to top" command keeps working with it hidden.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const PAGE_HEADER_MODES = ['auto', 'compact'] as const
export type PageHeaderMode = (typeof PAGE_HEADER_MODES)[number]

export const pageHeaderMode = defineSetting<PageHeaderMode>({
  key: 'ui.page_header',
  label: 'Page header',
  help: 'Auto condenses the page header once the region scrolls. Compact keeps it condensed from the first paint — the title stays, the eyebrow and description go — for screens where vertical room matters more than an introduction.',
  default: 'auto',
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseEnum(PAGE_HEADER_MODES),
  options: [
    { value: 'auto', label: 'Condense on scroll' },
    { value: 'compact', label: 'Always compact' },
  ],
})

export const lsatTimerVisible = defineSetting({
  key: 'lsat.timer.visible',
  label: 'Show the LSAT section timer when idle',
  help: 'The section clock in its dock while no section is running. A section in progress always shows its clock wherever this is set — hiding a running timer is the one failure the widget must never have (spec 043 FR-5).',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const libraryContents = defineSetting({
  key: 'lsat.library.contents',
  label: 'Show the library contents rail',
  help: 'The article and concept list beside the library reader. When hidden, a "Browse contents" disclosure opens it on demand at every width.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const libraryOutline = defineSetting({
  key: 'lsat.library.outline',
  label: 'Show the library outline',
  help: 'The "On this page" column beside a wide library reader. The entry\'s own headings stay in the document either way.',
  default: true,
  settableAt: INSTANCE_ONLY,
  lockable: false,
  parse: parseBoolean,
})

export const SETTING_CATALOG: SettingDefinition<unknown>[] = [
  // Ordered by key prefix: `SettingsForm` heads each group once, so keep a
  // prefix's settings together.
  hitlThreshold as SettingDefinition<unknown>,
  showCitationCounts as SettingDefinition<unknown>,
  railVisible as SettingDefinition<unknown>,
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
