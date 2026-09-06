import { describe, expect, it } from 'vitest'
import {
  layoutRowsForPath,
  MODULE_CATALOG,
  moduleForPath,
} from '@/lib/modules/catalog'
import { SETTING_CATALOG } from '@/lib/settings/catalog'

describe('MODULE_CATALOG', () => {
  it('registers the shipped modules in rail order', () => {
    // Matters joined the rail with spec 036 (BL-20260817-01/02): it is the
    // owner-scoped workspace the journey's later stages live in.
    expect(MODULE_CATALOG.map((m) => m.id)).toEqual([
      'home',
      'agents',
      'analysis',
      'graph',
      'lsat',
      'matters',
      'settings',
    ])
  })

  it('resolves a matter route to the matters module', () => {
    expect(moduleForPath('/matters').id).toBe('matters')
    expect(moduleForPath('/matters/smith-lease').id).toBe('matters')
  })

  it('resolves nested paths to the owning module', () => {
    expect(moduleForPath('/analysis').id).toBe('analysis')
    expect(moduleForPath('/').id).toBe('home')
    expect(moduleForPath('/unknown').id).toBe('home')
  })
})

describe('layoutRowsForPath', () => {
  // The Layout menu asks the catalog which module rows to show, so the route
  // names stay here instead of in the shell (BL-20260905-07).
  it('offers a module its own rows anywhere inside it', () => {
    expect(layoutRowsForPath('/lsat').map((r) => r.id)).toEqual(['timer'])
  })

  it('adds the rows a named sub-route contributes, on that sub-route only', () => {
    expect(layoutRowsForPath('/lsat/library').map((r) => r.id)).toEqual([
      'timer',
      'contents',
      'outline',
    ])
  })

  it('offers nothing for a module that declares nothing', () => {
    expect(layoutRowsForPath('/graph')).toEqual([])
    expect(layoutRowsForPath('/')).toEqual([])
  })

  it('declares a real, shippable setting for every row', () => {
    const keys = new Set(SETTING_CATALOG.map((s) => s.key))
    for (const row of layoutRowsForPath('/lsat/library')) {
      expect(keys.has(row.setting.key)).toBe(true)
      expect(row.label.length).toBeGreaterThan(0)
    }
  })
})

describe('SETTING_CATALOG', () => {
  it('ships every instance-scoped key', () => {
    // Exact equality on purpose: a setting added without a deliberate test
    // change is a setting nobody decided to ship.
    expect(SETTING_CATALOG.map((s) => s.key)).toEqual([
      'analysis.hitl_threshold',
      'graph.show_citation_counts',
      // Layout preferences (spec 050), contiguous so /settings heads them once.
      'ui.rail.visible',
      'ui.rail.expanded',
      'ui.sidebar.default_open',
      'ui.sidebar.side',
      'ui.inspector.default_open',
      'ui.inspector.side',
      'ui.masthead.breadcrumbs',
      'ui.masthead.scope_switcher',
      'ui.back_to_top',
      'ui.page_header',
      'lsat.timer.dock',
      'lsat.timer.visible',
      'lsat.timer.duration',
      'lsat.library.contents',
      'lsat.library.outline',
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
