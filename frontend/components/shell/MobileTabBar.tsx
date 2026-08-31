'use client'

import { MODULE_CATALOG } from '@/lib/modules/catalog'
import Link from 'next/link'

/**
 * Bottom navigation for viewports too narrow for the rail.
 *
 * A phone user gets the same primary destinations, in thumb reach, from the
 * same catalog — not a hamburger that hides the whole product behind a tap.
 */
export default function MobileTabBar({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Primary (compact)"
      data-testid="mobile-tabbar"
      className="flex h-[var(--shell-tabbar-h)] shrink-0 items-stretch border-t border-slate-800 bg-slate-950 md:hidden"
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
