/**
 * Command palette model.
 *
 * The palette is generated from the module catalog, never hand-listed: adding
 * a module to `lib/modules/catalog.ts` must be the only edit needed to make
 * it reachable from ⌘K. Closes BL-20260830-09.
 */

import type { AppModule } from '@/lib/modules/define'

export interface ShellCommand {
  id: string
  label: string
  group: string
  /** Secondary line — the route, or what the action does. */
  hint?: string
  /** Navigation commands carry an href; action commands carry an action. */
  href?: string
  action?:
    | 'toggle-sidebar'
    | 'toggle-inspector'
    | 'toggle-rail'
    | 'toggle-breadcrumbs'
    | 'reset-layout'
    | 'toggle-help'
    | 'back-to-top'
  /** Matched at label strength — the names a user would actually type. */
  aliases?: string[]
  /** Matched at substring strength only — supporting prose. */
  keywords?: string[]
  /**
   * Tie-break weight, low wins. A module landing page outranks one of its own
   * sub-links, which outranks a layout action — so searching "graph" offers
   * Knowledge Graph before "Graph · Attach to analysis".
   */
  rank: number
}

export function buildCommands(modules: AppModule[]): ShellCommand[] {
  const out: ShellCommand[] = []

  for (const mod of modules) {
    out.push({
      id: `go:${mod.id}`,
      label: mod.nav.label,
      group: 'Go to',
      hint: mod.nav.href,
      href: mod.nav.href,
      aliases: [mod.nav.short, mod.id],
      keywords: [mod.inspectorTitle],
      rank: 0,
    })
    for (const link of mod.sidebar ?? []) {
      // A module's own landing link is already the entry above.
      if (link.href === mod.nav.href) continue
      out.push({
        id: `go:${mod.id}:${link.href}`,
        label: `${mod.nav.short} · ${link.label}`,
        group: 'Go to',
        hint: link.href,
        href: link.href,
        keywords: [mod.nav.label, link.label],
        rank: 1,
      })
    }
  }

  out.push(
    {
      id: 'act:toggle-sidebar',
      label: 'Toggle contextual sidebar',
      group: 'Layout',
      hint: '[',
      action: 'toggle-sidebar',
      keywords: ['panel', 'nav', 'collapse'],
      rank: 2,
    },
    {
      id: 'act:toggle-inspector',
      label: 'Toggle inspector',
      group: 'Layout',
      hint: ']',
      action: 'toggle-inspector',
      keywords: ['panel', 'details', 'collapse'],
      rank: 2,
    },
    {
      id: 'act:toggle-rail',
      label: 'Toggle navigation rail',
      group: 'Layout',
      action: 'toggle-rail',
      keywords: ['rail', 'nav', 'hide', 'show', 'modules'],
      rank: 2,
    },
    {
      id: 'act:toggle-breadcrumbs',
      label: 'Toggle breadcrumb trail',
      group: 'Layout',
      action: 'toggle-breadcrumbs',
      keywords: ['masthead', 'trail', 'hide', 'show'],
      rank: 2,
    },
    {
      id: 'act:reset-layout',
      label: 'Reset layout to defaults',
      group: 'Layout',
      action: 'reset-layout',
      keywords: ['panels', 'rail', 'default', 'restore'],
      rank: 2,
    },
    {
      id: 'act:back-to-top',
      label: 'Scroll to top',
      group: 'Layout',
      hint: 'Home',
      action: 'back-to-top',
      keywords: ['scroll', 'up'],
      rank: 2,
    },
    {
      id: 'act:toggle-help',
      label: 'Keyboard shortcuts',
      group: 'Help',
      hint: '?',
      action: 'toggle-help',
      keywords: ['keys', 'bindings', 'accessibility'],
      rank: 2,
    },
  )

  return out
}

const PREFIX = 0
const LABEL_SUBSTRING = 1
const WEAK_SUBSTRING = 2
const NO_MATCH = -1

function scoreCommand(cmd: ShellCommand, q: string): number {
  const label = cmd.label.toLowerCase()
  const aliases = (cmd.aliases ?? []).map((a) => a.toLowerCase())
  if (label.startsWith(q) || aliases.some((a) => a.startsWith(q))) return PREFIX
  if (label.includes(q)) return LABEL_SUBSTRING
  const weak = [cmd.group, cmd.hint ?? '', ...(cmd.keywords ?? []), ...aliases]
    .join(' ')
    .toLowerCase()
  if (weak.includes(q)) return WEAK_SUBSTRING
  return NO_MATCH
}

/**
 * Rank by how strongly the query hits, then by what kind of thing matched.
 * Deliberately not fuzzy: a palette that guesses is a palette that fires the
 * wrong navigation, and this catalog is small enough that substring matching
 * finds everything.
 */
export function filterCommands(
  commands: ShellCommand[],
  query: string,
): ShellCommand[] {
  const q = query.trim().toLowerCase()
  if (!q) return commands

  const scored: { cmd: ShellCommand; score: number; order: number }[] = []
  commands.forEach((cmd, order) => {
    const score = scoreCommand(cmd, q)
    if (score !== NO_MATCH) scored.push({ cmd, score, order })
  })

  scored.sort(
    (a, b) => a.score - b.score || a.cmd.rank - b.cmd.rank || a.order - b.order,
  )
  return scored.map((s) => s.cmd)
}
