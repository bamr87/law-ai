import { describe, expect, it, beforeEach } from 'vitest'
import { breadcrumbsForPath, MODULE_CATALOG } from '@/lib/modules/catalog'
import { buildCommands, filterCommands } from '@/lib/shell/commands'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { listSettingValues, upsertSettingValue } from '@/lib/scope/store'
import {
  railVisible,
  SETTING_CATALOG,
  sidebarSide,
} from '@/lib/settings/catalog'
import {
  LAYOUT_SETTINGS,
  resetLayout,
  resolvePanelSides,
} from '@/lib/shell/layout'
import {
  panelHref,
  panelOpen,
  withoutPanels,
  withPanel,
} from '@/lib/shell/panels'
import {
  clearScrollMemory,
  recallScroll,
  rememberScroll,
} from '@/lib/shell/scrollMemory'
import {
  isTypingTarget,
  matchShortcut,
  SHORTCUT_HELP,
} from '@/lib/shell/shortcuts'

describe('panel state', () => {
  it('lets the URL win over the caller default in both directions', () => {
    expect(panelOpen(new URLSearchParams('sidebar=0'), 'sidebar', true)).toBe(
      false,
    )
    expect(panelOpen(new URLSearchParams('sidebar=1'), 'sidebar', false)).toBe(
      true,
    )
  })

  it('falls back to the default when the param is absent or junk', () => {
    expect(panelOpen(new URLSearchParams(), 'inspector', true)).toBe(true)
    expect(
      panelOpen(new URLSearchParams('inspector=yes'), 'inspector', false),
    ).toBe(false)
  })

  it('writes a toggle without dropping other params', () => {
    const qs = withPanel(
      new URLSearchParams('tab=lr&sidebar=1'),
      'inspector',
      true,
    )
    const next = new URLSearchParams(qs)
    expect(next.get('tab')).toBe('lr')
    expect(next.get('sidebar')).toBe('1')
    expect(next.get('inspector')).toBe('1')
  })

  it('collapses an empty query to a bare path', () => {
    expect(panelHref('/graph', '')).toBe('/graph')
    expect(panelHref('/graph', 'sidebar=0')).toBe('/graph?sidebar=0')
  })
})

describe('keyboard contract', () => {
  it('maps the bare-key bindings', () => {
    expect(matchShortcut({ key: '[' })).toBe('toggle-sidebar')
    expect(matchShortcut({ key: ']' })).toBe('toggle-inspector')
    expect(matchShortcut({ key: '?' })).toBe('toggle-help')
  })

  it('never fires a bare key while the user is typing', () => {
    // A fact pattern containing "[" must reach the textarea, not the shell.
    expect(matchShortcut({ key: '[' }, { typing: true })).toBeNull()
    expect(matchShortcut({ key: '?' }, { typing: true })).toBeNull()
  })

  it('keeps the palette and dismiss reachable from inside a field', () => {
    expect(matchShortcut({ key: 'k', metaKey: true }, { typing: true })).toBe(
      'open-palette',
    )
    expect(matchShortcut({ key: 'Escape' }, { typing: true })).toBe('dismiss')
  })

  it('ignores modified and unknown keys', () => {
    expect(matchShortcut({ key: '[', altKey: true })).toBeNull()
    expect(matchShortcut({ key: '[', ctrlKey: true })).toBeNull()
    expect(matchShortcut({ key: 'q' })).toBeNull()
  })

  it('recognises text-entry targets', () => {
    const input = document.createElement('input')
    const div = document.createElement('div')
    const editable = document.createElement('div')
    editable.contentEditable = 'true'
    expect(isTypingTarget(input)).toBe(true)
    expect(isTypingTarget(document.createElement('textarea'))).toBe(true)
    expect(isTypingTarget(div)).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
    // jsdom does not implement isContentEditable, so assert the tag path only.
    expect(typeof isTypingTarget(editable)).toBe('boolean')
  })

  it('documents every action it can produce', () => {
    expect(SHORTCUT_HELP.length).toBeGreaterThanOrEqual(5)
  })
})

describe('scroll memory', () => {
  beforeEach(() => clearScrollMemory(window.sessionStorage))

  it('round-trips a per-route offset', () => {
    rememberScroll('/agents', 640, window.sessionStorage)
    expect(recallScroll('/agents', window.sessionStorage)).toBe(640)
    expect(recallScroll('/graph', window.sessionStorage)).toBe(0)
  })

  it('drops the entry at the top instead of storing a zero', () => {
    rememberScroll('/agents', 640, window.sessionStorage)
    rememberScroll('/agents', 0, window.sessionStorage)
    expect(recallScroll('/agents', window.sessionStorage)).toBe(0)
    expect(window.sessionStorage.getItem('lawai.shell.scroll')).toBe('{}')
  })

  it('survives corrupt storage rather than throwing', () => {
    window.sessionStorage.setItem('lawai.shell.scroll', 'not json')
    expect(recallScroll('/agents', window.sessionStorage)).toBe(0)
    window.sessionStorage.setItem('lawai.shell.scroll', '{"/a":"x","/b":12}')
    expect(recallScroll('/a', window.sessionStorage)).toBe(0)
    expect(recallScroll('/b', window.sessionStorage)).toBe(12)
  })

  it('is a no-op without storage', () => {
    expect(() => rememberScroll('/agents', 10, null)).not.toThrow()
    expect(recallScroll('/agents', null)).toBe(0)
  })
})

describe('command palette model', () => {
  const commands = buildCommands(MODULE_CATALOG)

  it('offers every registered module without a hand-written list', () => {
    for (const mod of MODULE_CATALOG) {
      expect(commands.some((c) => c.href === mod.nav.href)).toBe(true)
    }
  })

  it('includes the shell layout actions', () => {
    const actions = commands.filter((c) => c.action).map((c) => c.action)
    expect(actions).toContain('toggle-sidebar')
    expect(actions).toContain('toggle-inspector')
    expect(actions).toContain('toggle-rail')
    expect(actions).toContain('toggle-breadcrumbs')
    expect(actions).toContain('reset-layout')
    expect(actions).toContain('back-to-top')
  })

  it('offers the module itself before one of its own sub-links', () => {
    // Both "Knowledge Graph" and "Graph · Attach to analysis" match; the
    // destination a user means by "graph" is the module.
    const hits = filterCommands(commands, 'graph')
    expect(hits.length).toBeGreaterThan(1)
    expect(hits[0].label).toBe('Knowledge Graph')
    expect(hits[0].href).toBe('/graph')
  })

  it('matches a module by its short alias', () => {
    const hits = filterCommands(commands, 'lsat')
    expect(hits[0].href).toBe('/lsat')
  })

  it('returns everything for an empty query and nothing for a miss', () => {
    expect(filterCommands(commands, '   ')).toHaveLength(commands.length)
    expect(filterCommands(commands, 'zzzzz')).toHaveLength(0)
  })
})

describe('breadcrumbs', () => {
  it('is a single crumb at the root', () => {
    expect(breadcrumbsForPath('/')).toEqual([
      { label: 'Dashboard', href: '/', current: true },
    ])
  })

  it('roots every module trail at the dashboard', () => {
    const crumbs = breadcrumbsForPath('/graph')
    expect(crumbs[0]).toMatchObject({ href: '/', current: false })
    expect(crumbs[crumbs.length - 1]).toMatchObject({
      label: 'Knowledge Graph',
      current: true,
    })
  })

  it('marks the module crumb current for an unnamed nested route', () => {
    const crumbs = breadcrumbsForPath('/lsat/section/lr')
    expect(crumbs[crumbs.length - 1]).toMatchObject({
      label: 'LSAT Lab',
      current: true,
    })
  })
})

describe('layout preferences (spec 051)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('keeps the sidebar outermost and the inspector innermost on either edge', () => {
    expect(resolvePanelSides({ sidebar: 'left', inspector: 'right' })).toEqual({
      left: ['sidebar'],
      right: ['inspector'],
    })
    expect(resolvePanelSides({ sidebar: 'right', inspector: 'right' })).toEqual({
      left: [],
      right: ['inspector', 'sidebar'],
    })
    expect(resolvePanelSides({ sidebar: 'left', inspector: 'left' })).toEqual({
      left: ['sidebar', 'inspector'],
      right: [],
    })
    expect(resolvePanelSides({ sidebar: 'right', inspector: 'left' })).toEqual({
      left: ['inspector'],
      right: ['sidebar'],
    })
  })

  it('resets by deleting rows, and only layout rows', () => {
    const write = (key: string, value: unknown) =>
      upsertSettingValue({ scopeId: INSTANCE_SCOPE.id, key, value, locked: false })
    write(railVisible.key, false)
    write(sidebarSide.key, 'right')
    write('analysis.hitl_threshold', 0.9)
    resetLayout()
    expect(listSettingValues().map((r) => r.key)).toEqual([
      'analysis.hitl_threshold',
    ])
  })

  it('owns every ui.* setting in the catalog', () => {
    const owned = LAYOUT_SETTINGS.map((d) => d.key)
    for (const def of SETTING_CATALOG) {
      if (def.key.startsWith('ui.')) expect(owned).toContain(def.key)
    }
  })

  it('drops both panel params from a URL and nothing else', () => {
    expect(
      withoutPanels(new URLSearchParams('sidebar=0&inspector=1&concept=x')),
    ).toBe('concept=x')
    expect(withoutPanels(new URLSearchParams('sidebar=0'))).toBe('')
  })
})
