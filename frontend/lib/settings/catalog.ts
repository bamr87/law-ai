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
  help: 'When no `inspector` query param is set, open the right-hand inspector panel.',
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

export const SETTING_CATALOG: SettingDefinition<unknown>[] = [
  hitlThreshold as SettingDefinition<unknown>,
  showCitationCounts as SettingDefinition<unknown>,
  inspectorDefaultOpen as SettingDefinition<unknown>,
  lsatTimerDock as SettingDefinition<unknown>,
]
