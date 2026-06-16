'use client'

import { cn } from '@/lib/cn'
import { useAgents } from '@/lib/queries'
import { useHydrated } from '@/lib/useHydrated'
import {
  Bot,
  GraduationCap,
  LayoutDashboard,
  Menu,
  Network,
  Scale,
  X,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

const LINKS: { href: string; label: string; short: string; icon: LucideIcon }[] =
  [
    { href: '/', label: 'Dashboard', short: 'Home', icon: LayoutDashboard },
    { href: '/agents', label: 'Agent Ops', short: 'Agents', icon: Bot },
    { href: '/analysis', label: 'Analysis Studio', short: 'Analysis', icon: Scale },
    { href: '/graph', label: 'Knowledge Graph', short: 'Graph', icon: Network },
    { href: '/lsat', label: 'LSAT Lab', short: 'LSAT', icon: GraduationCap },
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
        'inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1 text-xs',
        online
          ? 'border-success/20 bg-success/10 text-success'
          : offline
            ? 'border-danger/20 bg-danger/10 text-danger'
            : 'border-border bg-surface-2 text-muted',
        className,
      )}
    >
      <span className="relative flex h-2 w-2">
        {online && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
        )}
        <span
          className={cn(
            'relative inline-flex h-2 w-2 rounded-full',
            online ? 'bg-success' : offline ? 'bg-danger' : 'bg-subtle',
          )}
        />
      </span>
      <span>{online ? 'Online' : offline ? 'Offline' : '…'}</span>
      <span className="text-success/60">·</span>
      <span>Local</span>
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
    <nav className="sticky top-0 z-40 border-b border-border bg-canvas/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:h-16 sm:px-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 whitespace-nowrap"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-strong shadow-lg shadow-brand/20">
            <span className="text-sm font-bold text-white">LG</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-ink sm:text-xl">
            LawGraph<span className="text-brand"> AI</span>
          </span>
        </Link>

        <div className="ml-2 hidden flex-1 items-center gap-0.5 text-sm md:flex">
          {LINKS.map(({ href, label, short, icon: Icon }) => {
            const active = isActive(href)
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 transition lg:px-3',
                  active
                    ? 'bg-brand/15 text-brand ring-1 ring-inset ring-brand/30'
                    : 'text-muted hover:bg-surface-2 hover:text-ink',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                <span className="lg:hidden">{short}</span>
                <span className="hidden lg:inline">{label}</span>
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
          className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface-2 text-ink transition hover:border-brand/40 md:hidden"
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
          className="border-t border-border bg-canvas/95 px-4 py-3 md:hidden"
        >
          <ul className="flex flex-col gap-1 text-sm">
            {LINKS.map(({ href, label, icon: Icon }) => {
              const active = isActive(href)
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-3 py-2 transition',
                      active
                        ? 'bg-brand/15 text-brand ring-1 ring-inset ring-brand/30'
                        : 'text-muted hover:bg-surface-2 hover:text-ink',
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                    {label}
                  </Link>
                </li>
              )
            })}
          </ul>
          <div className="mt-3">
            <StatusPill />
          </div>
        </div>
      )}
    </nav>
  )
}
