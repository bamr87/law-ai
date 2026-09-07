'use client'

import { MODULE_CATALOG, moduleForPath } from '@/lib/modules/catalog'
import { railExpanded } from '@/lib/settings/catalog'
import Link from 'next/link'
import { useMediaQuery, WIDE_QUERY } from './useMediaQuery'
import { useSetting } from './useSetting'

/**
 * Primary navigation. Structurally unable to scroll away: it is a full-height
 * column inside the shell's non-scrolling row, and scrolls *itself* only if
 * the catalog ever outgrows the viewport.
 *
 * Hidden below `md`, where `MobileTabBar` carries the same catalog.
 *
 * Glyph-only by default, labelled on request (`ui.rail.expanded`,
 * BL-20260831-06). The labelled variant needs a column the narrower layouts do
 * not have to spare, so it applies at `xl` and wider only; below that the
 * preference is remembered and simply not in effect. In the labelled variant
 * the name is *visible* text and the `title`/`sr-only` pair goes away — a
 * visible label plus an identical screen-reader label is the same name twice.
 */
export default function NavRail({ pathname }: { pathname: string }) {
  const [expandPreferred] = useSetting(railExpanded)
  const wide = useMediaQuery(WIDE_QUERY)
  const expanded = expandPreferred && wide
  // Which entry lights up is the catalog's answer, not a prefix test here: a
  // module may own a route that does not nest under its own href — /autonomy
  // belongs to Agent Ops — and `startsWith(mod.nav.href)` left the rail
  // showing nothing at all on those (BL-20260906-21). Asking `moduleForPath`
  // also means exactly one entry can ever be current.
  const owner = moduleForPath(pathname)
  // `moduleForPath` falls back to Home for a route nobody claims. Home's entry
  // is current at "/" and nowhere else, so an unclaimed route lights nothing
  // rather than pointing at the dashboard.
  const activeId =
    owner.nav.href === '/' && pathname !== '/' ? null : owner.id

  return (
    <nav
      aria-label="Primary"
      data-testid="nav-rail"
      data-expanded={expanded ? 'true' : undefined}
      className={
        'shell-panel-scroll hidden h-full shrink-0 flex-col gap-1 border-r border-slate-800 bg-slate-950 py-3 md:flex ' +
        (expanded
          ? 'w-[var(--shell-rail-w-expanded)] items-stretch px-2'
          : 'w-[var(--shell-rail-w)] items-center')
      }
    >
      {MODULE_CATALOG.map((mod) => {
        const active = mod.id === activeId
        return (
          <Link
            key={mod.id}
            href={mod.nav.href}
            title={expanded ? undefined : mod.nav.label}
            aria-current={active ? 'page' : undefined}
            className={
              'relative flex h-10 shrink-0 items-center rounded-md text-[11px] font-semibold tracking-tight transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
              (expanded ? 'w-full gap-2 px-2 ' : 'w-10 justify-center ') +
              (active
                ? 'bg-blue-600/15 text-blue-300 ring-1 ring-inset ring-blue-500/30'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-white')
            }
          >
            {/* Active marker on the rail edge — colour alone is not a state
             * indicator (WCAG 1.4.1). */}
            {active && (
              <span
                aria-hidden="true"
                className={
                  'absolute h-6 w-1 rounded-r-full bg-blue-400 ' +
                  // Both variants park the marker on the rail's own edge; the
                  // expanded rail has 8px of padding, the glyph rail 12px.
                  (expanded ? '-left-2' : '-left-3')
                }
              />
            )}
            <span
              aria-hidden="true"
              className={expanded ? 'w-6 shrink-0 text-center' : undefined}
            >
              {mod.nav.glyph}
            </span>
            <span className={expanded ? 'truncate' : 'sr-only'}>
              {mod.nav.label}
            </span>
          </Link>
        )
      })}
    </nav>
  )
}
