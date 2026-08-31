import { defineSetting, INSTANCE_ONLY, parseBoolean, parseNumber } from './define'
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

export const SETTING_CATALOG: SettingDefinition<unknown>[] = [
  hitlThreshold as SettingDefinition<unknown>,
  showCitationCounts as SettingDefinition<unknown>,
  inspectorDefaultOpen as SettingDefinition<unknown>,
]
