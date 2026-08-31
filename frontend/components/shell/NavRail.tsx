'use client'

import { MODULE_CATALOG } from '@/lib/modules/catalog'
import Link from 'next/link'

export default function NavRail({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Primary"
      className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-slate-800 bg-slate-950 py-3"
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
              'flex h-10 w-10 items-center justify-center rounded-md text-[11px] font-semibold tracking-tight transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
              (active
                ? 'bg-blue-600/15 text-blue-300 ring-1 ring-inset ring-blue-500/30'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-white')
            }
          >
            <span aria-hidden="true">{mod.nav.glyph}</span>
            <span className="sr-only">{mod.nav.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
