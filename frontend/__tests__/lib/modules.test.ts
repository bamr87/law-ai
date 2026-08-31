import { describe, expect, it } from 'vitest'
import { MODULE_CATALOG, moduleForPath } from '@/lib/modules/catalog'
import { SETTING_CATALOG } from '@/lib/settings/catalog'

describe('MODULE_CATALOG', () => {
  it('registers the six v1 modules including settings', () => {
    expect(MODULE_CATALOG.map((m) => m.id)).toEqual([
      'home',
      'agents',
      'analysis',
      'graph',
      'lsat',
      'settings',
    ])
  })

  it('resolves nested paths to the owning module', () => {
    expect(moduleForPath('/analysis').id).toBe('analysis')
    expect(moduleForPath('/').id).toBe('home')
    expect(moduleForPath('/unknown').id).toBe('home')
  })
})

describe('SETTING_CATALOG', () => {
  it('ships every instance-scoped key', () => {
    // Exact equality on purpose: a setting added without a deliberate test
    // change is a setting nobody decided to ship.
    expect(SETTING_CATALOG.map((s) => s.key)).toEqual([
      'analysis.hitl_threshold',
      'graph.show_citation_counts',
      'ui.inspector.default_open',
      'lsat.timer.dock',
    ])
  })

  it('gives every enum setting options its parser accepts', () => {
    for (const def of SETTING_CATALOG) {
      if (!def.options) continue
      expect(def.options.length).toBeGreaterThan(1)
      for (const o of def.options) expect(def.parse(o.value)).toBe(o.value)
      expect(def.parse(def.default)).toBe(def.default)
    }
  })
})
