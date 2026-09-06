import { describe, expect, it } from 'vitest'
import {
  agentsModule,
  breadcrumbsForPath,
  moduleForPath,
} from '@/lib/modules/catalog'

/**
 * BL-20260511-03. `/autonomy` is an Agent-Ops view, not a seventh module: it
 * answers "what did the nightly loops do" about the same agents that module
 * lists. The catalog therefore has to own the route without owning a rail
 * slot, or the page renders under a "Dashboard" breadcrumb that lies.
 */
describe('/autonomy route ownership', () => {
  it('is linked from the Agent Ops sidebar', () => {
    const hrefs = (agentsModule.sidebar ?? []).map((l) => l.href)
    expect(hrefs).toContain('/autonomy')
  })

  it('resolves to the Agent Ops module even though it is not nested', () => {
    expect(moduleForPath('/autonomy').id).toBe('agents')
  })

  it('does not steal routes from a module that owns them outright', () => {
    // `/settings` is also an Agent-Ops sidebar link, but Settings is a module.
    expect(moduleForPath('/settings').id).toBe('settings')
    expect(moduleForPath('/unknown').id).toBe('home')
  })

  it('builds a breadcrumb trail that names the page', () => {
    expect(breadcrumbsForPath('/autonomy')).toEqual([
      { label: 'Dashboard', href: '/', current: false },
      { label: 'Agent Ops', href: '/agents', current: false },
      { label: 'Autonomy panels', href: '/autonomy', current: true },
    ])
  })
})
