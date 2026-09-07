'use client'

import { MODULE_CATALOG, moduleForPath } from '@/lib/modules/catalog'
import Link from 'next/link'

/**
 * Bottom navigation for viewports too narrow for the rail.
 *
 * A phone user gets the same primary destinations, in thumb reach, from the
 * same catalog — not a hamburger that hides the whole product behind a tap.
 */
export default function MobileTabBar({ pathname }: { pathname: string }) {
  // Same rule as the rail: the catalog decides which module owns this route,
  // including the ones a module claims through a sidebar link (BL-20260906-21).
  const owner = moduleForPath(pathname)
  // `moduleForPath` falls back to Home for a route nobody claims. Home's entry
  // is current at "/" and nowhere else, so an unclaimed route lights nothing
  // rather than pointing at the dashboard.
  const activeId =
    owner.nav.href === '/' && pathname !== '/' ? null : owner.id
  return (
    <nav
      aria-label="Primary (compact)"
      data-testid="mobile-tabbar"
      className="flex h-[var(--shell-tabbar-h)] shrink-0 items-stretch border-t border-slate-800 bg-slate-950 md:hidden"
    >
      {MODULE_CATALOG.map((mod) => {
        const active = mod.id === activeId
        return (
          <Link
            key={mod.id}
            href={mod.nav.href}
            aria-current={active ? 'page' : undefined}
            className={
              'flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue-400 ' +
              (active ? 'text-blue-300' : 'text-slate-400')
            }
          >
            <span aria-hidden="true" className="text-xs font-semibold">
              {mod.nav.glyph}
            </span>
            <span className="truncate px-1">{mod.nav.short}</span>
          </Link>
        )
      })}
    </nav>
  )
}
