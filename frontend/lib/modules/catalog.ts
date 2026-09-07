import {
  libraryContents,
  libraryOutline,
  lsatTimerVisible,
} from '@/lib/settings/catalog'
import { defineModule, type AppModule, type ModuleLayoutRow } from './define'

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
    // BL-20260811-01: the HITL quarantine queue had only operator surfaces
    // (Django admin, `manage.py review_queue`). It is Agent-Ops work — what
    // the ingestion agents produced that a human still has to accept.
    { href: '/agents/reviews', label: 'Review queue' },
    // BL-20260511-03: the autonomy panels are an Agent-Ops view, not a module
    // of their own — they answer "what did the nightly loops do" about the
    // same agents this module lists.
    { href: '/autonomy', label: 'Autonomy panels' },
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
    {
      href: '/lsat/library',
      label: 'Library & concepts',
      layout: [
        {
          id: 'contents',
          label: 'Library contents rail',
          setting: libraryContents,
        },
        { id: 'outline', label: 'Library outline', setting: libraryOutline },
      ],
    },
    { href: '/settings', label: 'Instance settings' },
  ],
  layout: [
    {
      id: 'timer',
      label: 'Section timer when idle',
      setting: lsatTimerVisible,
    },
  ],
  dockWidgets: ['lsat-timer'],
  inspectorTitle: 'LSAT Lab',
  inspectorBody:
    'API-backed drills and HITL authoring in the lab; long-form articles and the concept catalog in the library. Study aid, not legal advice.',
  upl: true,
})

export const mattersModule = defineModule({
  id: 'matters',
  nav: { label: 'Matters', short: 'Matters', href: '/matters', glyph: 'Mt' },
  sidebar: [
    { href: '/matters', label: 'Matters & deadlines' },
    { href: '/matters/account', label: 'Your data' },
    { href: '/analysis', label: 'Run an analysis' },
  ],
  inspectorTitle: 'Matters',
  inspectorBody:
    'One container per legal question: its research, the authorities you verified, and the deadlines you entered. Per-account and never reachable by a shared key. Due dates are yours — nothing computes a court deadline.',
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
  mattersModule,
  settingsModule,
]

export function moduleForPath(pathname: string): AppModule {
  const exact = MODULE_CATALOG.find((m) => m.nav.href === pathname)
  if (exact) return exact
  const nested = MODULE_CATALOG.find(
    (m) => m.nav.href !== '/' && pathname.startsWith(m.nav.href),
  )
  if (nested) return nested
  // A module may own a route that does not nest under its own href —
  // /autonomy belongs to Agent Ops (BL-20260511-03). A sidebar link is
  // already the catalog's statement that a module owns a route, so reuse it
  // rather than teaching the shell a second registry.
  const linked = MODULE_CATALOG.find((m) =>
    (m.sidebar ?? []).some(
      (link) => link.href !== '/' && pathname.startsWith(link.href),
    ),
  )
  return linked ?? homeModule
}

/**
 * The Layout-menu rows on offer here: the active module's own rows, plus the
 * rows any sidebar sub-route it names contributes while the user is on it.
 *
 * The menu asks the catalog rather than testing route prefixes itself — a
 * "Section timer" row on the graph page would be a promise about nothing, and
 * deciding that is the module registry's job, not the shell's
 * (BL-20260905-07).
 */
export function layoutRowsForPath(pathname: string): ModuleLayoutRow[] {
  const mod = moduleForPath(pathname)
  const rows: ModuleLayoutRow[] = [...(mod.layout ?? [])]
  for (const link of mod.sidebar ?? []) {
    if (link.layout && link.href !== mod.nav.href && pathname.startsWith(link.href)) {
      rows.push(...link.layout)
    }
  }
  return rows
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
