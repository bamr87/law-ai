'use client'

import { moduleForPath } from '@/lib/modules/catalog'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

/**
 * Contextual navigation for the active module. Scrolls independently of the
 * page: a long link list must not drag the reader's content with it, and a
 * short one must not scroll at all.
 */
export default function ContextSidebar() {
  const pathname = usePathname() || '/'
  const mod = moduleForPath(pathname)
  const links = mod.sidebar ?? []

  return (
    <div className="shell-panel-scroll flex h-full flex-col px-3 py-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {mod.nav.label}
      </p>
      {links.length === 0 ? (
        <p className="mt-3 text-xs text-slate-400">No contextual links.</p>
      ) : (
        <ul className="mt-3 space-y-1">
          {links.map((link) => {
            const active = pathname === link.href
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? 'page' : undefined}
                  className={
                    'block rounded-md px-2 py-1.5 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
                    (active
                      ? 'bg-blue-600/15 text-blue-300'
                      : 'text-slate-300 hover:bg-slate-800/60 hover:text-white')
                  }
                >
                  {link.label}
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
