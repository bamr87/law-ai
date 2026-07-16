'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

const LINKS = [
  { href: '/', label: 'Dashboard', short: 'Home' },
  { href: '/agents', label: 'Agent Ops', short: 'Agents' },
  { href: '/analysis', label: 'Analysis Studio', short: 'Analysis' },
  { href: '/graph', label: 'Knowledge Graph', short: 'Graph' },
  { href: '/lsat', label: 'LSAT Lab', short: 'LSAT' },
] as const

export default function NavBar() {
  const pathname = usePathname() || '/'
  const [open, setOpen] = useState(false)

  // Close mobile menu when route changes.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  return (
    <nav className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:h-16 sm:px-6">
        {/* Brand */}
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 whitespace-nowrap"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/20">
            <span className="font-bold text-white">LG</span>
          </div>
          <span className="text-lg font-semibold tracking-tight sm:text-xl">
            Law<span className="text-blue-400"> AI</span>
          </span>
        </Link>

        {/* Desktop links — short labels at md, full labels at xl */}
        <div className="ml-2 hidden flex-1 items-center gap-0.5 text-sm md:flex">
          {LINKS.map((link) => {
            const active = isActive(link.href)
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={
                  'whitespace-nowrap rounded-md px-2.5 py-1.5 transition lg:px-3 ' +
                  (active
                    ? 'bg-blue-600/15 text-blue-300 ring-1 ring-inset ring-blue-500/30'
                    : 'text-slate-300 hover:bg-slate-800/60 hover:text-white')
                }
              >
                <span className="lg:hidden">{link.short}</span>
                <span className="hidden lg:inline">{link.label}</span>
              </Link>
            )
          })}
        </div>

        {/* Right-side status pill (desktop) */}
        <div
          className="ml-auto hidden shrink-0 items-center gap-2 whitespace-nowrap rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300 md:flex"
          title="Connected to local backend on :8000"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <span>v0.1.1</span>
          <span className="text-emerald-500/60">·</span>
          <span>Local</span>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-700 bg-slate-900/60 text-slate-200 transition hover:border-blue-500/40 hover:text-white md:hidden"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-5 w-5"
            aria-hidden="true"
          >
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l12 12M18 6L6 18" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h16M4 17h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu drawer */}
      {open && (
        <div
          id="mobile-nav"
          className="border-t border-slate-800 bg-slate-950/95 px-4 py-3 md:hidden"
        >
          <ul className="flex flex-col gap-1 text-sm">
            {LINKS.map((link) => {
              const active = isActive(link.href)
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    aria-current={active ? 'page' : undefined}
                    className={
                      'block rounded-md px-3 py-2 transition ' +
                      (active
                        ? 'bg-blue-600/15 text-blue-300 ring-1 ring-inset ring-blue-500/30'
                        : 'text-slate-300 hover:bg-slate-800/60 hover:text-white')
                    }
                  >
                    {link.label}
                  </Link>
                </li>
              )
            })}
          </ul>
          <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
            v0.1.1 · Local Mode
          </div>
        </div>
      )}
    </nav>
  )
}
