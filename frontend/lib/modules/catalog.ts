import { defineModule, type AppModule } from './define'

export const homeModule = defineModule({
  id: 'home',
  nav: { label: 'Dashboard', short: 'Home', href: '/', glyph: 'LA' },
  inspectorTitle: 'Dashboard',
  inspectorBody:
    'Open-source agent-orchestrated legal intelligence. Pick a module from the rail.',
  upl: false,
})

export const agentsModule = defineModule({
  id: 'agents',
  nav: { label: 'Agent Ops', short: 'Agents', href: '/agents', glyph: 'Ag' },
  sidebar: [
    { href: '/agents', label: 'Registry & runs' },
    { href: '/settings', label: 'Instance settings' },
  ],
  inspectorTitle: 'Agent Ops',
  inspectorBody:
    'Live registry, audit-grade run trail, BACKLOG triage, spec lifecycle. Backed by /api/agents/*.',
  upl: false,
})

export const analysisModule = defineModule({
  id: 'analysis',
  nav: {
    label: 'Analysis Studio',
    short: 'Analysis',
    href: '/analysis',
    glyph: 'IR',
  },
  sidebar: [
    { href: '/analysis', label: 'Run analysis' },
    { href: '/graph', label: 'Open knowledge graph' },
  ],
  inspectorTitle: 'Analysis Studio',
  inspectorBody:
    'LegalAnalyst and PrecedentHunter run in parallel. Output is not legal advice. Verify every citation against the issuing authority.',
  upl: true,
})

export const graphModule = defineModule({
  id: 'graph',
  nav: {
    label: 'Knowledge Graph',
    short: 'Graph',
    href: '/graph',
    glyph: 'Kg',
  },
  sidebar: [
    { href: '/graph', label: 'Case neighborhood' },
    { href: '/analysis', label: 'Attach to analysis' },
  ],
  inspectorTitle: 'Knowledge Graph',
  inspectorBody:
    'Cytoscape view of cases and CITES edges. Node size/color by citation count is litigation frequency, not correctness.',
  upl: false,
})

export const lsatModule = defineModule({
  id: 'lsat',
  nav: { label: 'LSAT Lab', short: 'LSAT', href: '/lsat', glyph: 'LS' },
  sidebar: [
    { href: '/lsat', label: 'Practice lab' },
    { href: '/lsat/library', label: 'Knowledge library' },
    { href: '/settings', label: 'Instance settings' },
  ],
  inspectorTitle: 'LSAT Lab',
  inspectorBody:
    'API-backed drills, concepts, and HITL authoring, plus a reading library on exam structure and method. Study aid, not legal advice.',
  upl: true,
})

export const settingsModule = defineModule({
  id: 'settings',
  nav: { label: 'Settings', short: 'Settings', href: '/settings', glyph: '⚙' },
  sidebar: [{ href: '/settings', label: 'Instance' }],
  inspectorTitle: 'Settings',
  inspectorBody:
    'Instance-scoped values with inheritance provenance. Org/team scopes are not live (spec 036 NG3). Override is explicit — focusing a field does not write.',
  upl: false,
})

export const MODULE_CATALOG: AppModule[] = [
  homeModule,
  agentsModule,
  analysisModule,
  graphModule,
  lsatModule,
  settingsModule,
]

export function moduleForPath(pathname: string): AppModule {
  const exact = MODULE_CATALOG.find((m) => m.nav.href === pathname)
  if (exact) return exact
  const nested = MODULE_CATALOG.find(
    (m) => m.nav.href !== '/' && pathname.startsWith(m.nav.href),
  )
  return nested ?? homeModule
}

export interface Crumb {
  label: string
  href: string
  /** The trailing crumb — rendered as text, not a link. */
  current: boolean
}

/**
 * Breadcrumb trail for the masthead. Derived from the catalog so a new module
 * gets a trail for free; `AppShell` never learns a route name.
 *
 * Home is always the root crumb — a user who has drilled into a module needs
 * one click back to the top, and "where am I" is the question the masthead is
 * there to answer.
 */
export function breadcrumbsForPath(pathname: string): Crumb[] {
  const mod = moduleForPath(pathname)
  if (mod.nav.href === '/' && pathname === '/') {
    return [{ label: homeModule.nav.label, href: '/', current: true }]
  }

  const crumbs: Crumb[] = [
    { label: homeModule.nav.label, href: '/', current: false },
    {
      label: mod.nav.label,
      href: mod.nav.href,
      current: pathname === mod.nav.href,
    },
  ]

  const leaf = (mod.sidebar ?? []).find(
    (l) => l.href === pathname && l.href !== mod.nav.href,
  )
  if (leaf) {
    crumbs.push({ label: leaf.label, href: leaf.href, current: true })
  } else if (pathname !== mod.nav.href) {
    // A nested route the catalog doesn't name: keep the module crumb as the
    // current one rather than inventing a label from the URL segment.
    crumbs[crumbs.length - 1].current = true
  }
  return crumbs
}
