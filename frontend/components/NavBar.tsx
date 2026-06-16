'use client'

import { cn } from '@/lib/cn'
import { useAgents } from '@/lib/queries'
import { useHydrated } from '@/lib/useHydrated'
import { Menu, X } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

const LINKS = [
  { href: '/', label: 'Dashboard', short: 'Home' },
  { href: '/agents', label: 'Agent Ops', short: 'Agents' },
  { href: '/analysis', label: 'Analysis Studio', short: 'Analysis' },
  { href: '/graph', label: 'Knowledge Graph', short: 'Graph' },
  { href: '/lsat', label: 'LSAT Lab', short: 'LSAT' },
]

function StatusPill({ className }: { className?: string }) {
  const hydrated = useHydrated()
  const { isSuccess, isError } = useAgents()
  const online = hydrated && isSuccess
  const offline = hydrated && isError
  return (
    <span
      title={
        online
          ? 'Connected to local backend on :8000'
          : offline
            ? 'Backend unreachable on :8000'
            : 'Connecting…'
      }
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-border bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-muted',
        className,
      )}
    >
      <span
        className={cn(
          'inline-block h-1.5 w-1.5 rounded-full',
          online ? 'bg-success' : offline ? 'bg-danger' : 'bg-subtle',
        )}
      />
      {online ? 'Online' : offline ? 'Offline' : '…'}
      <span className="text-subtle">· Local</span>
    </span>
  )
}

export default function NavBar() {
  const pathname = usePathname() || '/'
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setOpen(false)
  }, [pathname])

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  return (
    <nav
      aria-label="Primary"
      className="sticky top-0 z-40 border-b border-border bg-surface-2/80 backdrop-blur"
    >
      <div className="flex h-14 items-center gap-4 px-4 sm:h-16 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand text-[11px] font-bold text-white">
            LG
          </span>
          <span className="text-base font-semibold tracking-tight text-ink">
            LawGraph<span className="text-brand"> AI</span>
          </span>
        </Link>

        {/* Underline tabs — EDGAR's .nav-link pattern */}
        <div className="ml-2 hidden flex-1 items-center gap-5 md:flex">
          {LINKS.map(({ href, label }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'whitespace-nowrap border-b-2 py-1 text-sm font-semibold transition',
                  active
                    ? 'border-brand text-brand'
                    : 'border-transparent text-muted hover:text-ink',
                )}
              >
                {label}
              </Link>
            )
          })}
        </div>

        <StatusPill className="ml-auto hidden md:inline-flex" />

        <button
          type="button"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface text-ink transition hover:border-brand/40 md:hidden"
        >
          {open ? (
            <X className="h-5 w-5" aria-hidden />
          ) : (
            <Menu className="h-5 w-5" aria-hidden />
          )}
        </button>
      </div>

      {open && (
        <div
          id="mobile-nav"
          className="border-t border-border px-4 py-2 md:hidden"
        >
          <ul className="flex flex-col">
            {LINKS.map(({ href, label }) => {
              const active = isActive(href)
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'block border-l-2 px-3 py-2 text-sm font-semibold transition',
                      active
                        ? 'border-brand bg-brand-soft text-brand'
                        : 'border-transparent text-muted hover:text-ink',
                    )}
                  >
                    {label}
                  </Link>
                </li>
              )
            })}
          </ul>
          <div className="mt-2 pl-3">
            <StatusPill />
          </div>
        </div>
      )}
    </nav>
  )
}
