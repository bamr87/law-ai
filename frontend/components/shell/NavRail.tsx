'use client'

import { MODULE_CATALOG } from '@/lib/modules/catalog'
import Link from 'next/link'

/**
 * Primary navigation. Structurally unable to scroll away: it is a full-height
 * column inside the shell's non-scrolling row, and scrolls *itself* only if
 * the catalog ever outgrows the viewport.
 *
 * Hidden below `md`, where `MobileTabBar` carries the same catalog.
 */
export default function NavRail({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Primary"
      data-testid="nav-rail"
      className="shell-panel-scroll hidden h-full w-[var(--shell-rail-w)] shrink-0 flex-col items-center gap-1 border-r border-slate-800 bg-slate-950 py-3 md:flex"
    >
      {MODULE_CATALOG.map((mod) => {
        const active =
          mod.nav.href === '/'
            ? pathname === '/'
            : pathname.startsWith(mod.nav.href)
        return (
          <Link
            key={mod.id}
            href={mod.nav.href}
            title={mod.nav.label}
            aria-current={active ? 'page' : undefined}
            className={
              'relative flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold tracking-tight transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
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
                className="absolute -left-3 h-6 w-1 rounded-r-full bg-blue-400"
              />
            )}
            <span aria-hidden="true">{mod.nav.glyph}</span>
            <span className="sr-only">{mod.nav.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
