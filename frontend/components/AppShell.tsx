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
import { useEffect, useState, type ReactNode } from 'react'

interface NavItem {
  href: string
  label: string
  icon: LucideIcon
}

const SECTIONS: NavItem[] = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/agents', label: 'Agent Ops', icon: Bot },
  { href: '/analysis', label: 'Analysis Studio', icon: Scale },
  { href: '/graph', label: 'Knowledge Graph', icon: Network },
  { href: '/lsat', label: 'LSAT Lab', icon: GraduationCap },
]

function isActive(pathname: string, href: string) {
  return href === '/' ? pathname === '/' : pathname.startsWith(href)
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-xs font-bold text-white">
        LG
      </span>
      <span className="text-base font-semibold tracking-tight text-ink">
        LawGraph<span className="text-brand"> AI</span>
      </span>
    </Link>
  )
}

function StatusPill() {
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
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-muted"
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

/** The shared sidebar body — brand, section nav, status. Reused on desktop and
 *  inside the mobile drawer. */
function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname() || '/'
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4 sm:h-16">
        <Brand />
      </div>

      <nav aria-label="Sections" className="flex-1 overflow-y-auto px-3 py-2">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wide text-subtle">
          Sections
        </p>
        <ul className="space-y-0.5">
          {SECTIONS.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href)
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  onClick={onNavigate}
                  className={cn(
                    'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition',
                    active
                      ? 'bg-brand-soft text-brand shadow-[inset_2px_0_0_0_var(--color-brand)]'
                      : 'text-muted hover:bg-surface hover:text-ink',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden />
                  {label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-border px-4 py-3">
        <StatusPill />
      </div>
    </div>
  )
}

/**
 * App layout: a fixed left sidebar for section navigation + a scrolling content
 * area. On small screens the sidebar collapses into a slide-in drawer behind a
 * top bar. EDGAR tokens throughout.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  // Close the mobile drawer on navigation.
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  return (
    <div className="flex min-h-svh">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-svh w-60 shrink-0 border-r border-border bg-surface-2/40 md:block">
        <SidebarBody />
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="animate-fade-in absolute inset-y-0 left-0 w-64 border-r border-border bg-canvas shadow-[var(--shadow-pop)]">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="absolute right-2 top-3 rounded-md p-1 text-subtle hover:bg-surface hover:text-ink"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
            <SidebarBody onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-canvas/80 px-4 backdrop-blur md:hidden">
          <button
            type="button"
            aria-label="Open menu"
            aria-expanded={open}
            onClick={() => setOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface text-ink hover:border-brand/40"
          >
            <Menu className="h-5 w-5" aria-hidden />
          </button>
          <Brand />
        </div>

        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
}
