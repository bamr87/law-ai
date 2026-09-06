'use client'

import { breadcrumbsForPath } from '@/lib/modules/catalog'
import Link from 'next/link'
import type { ReactNode } from 'react'
import AccountMenu from './AccountMenu'
import ScopeSwitcher from './ScopeSwitcher'

/**
 * The one bar that is always on screen. It is a flex row of the shell, not a
 * `position: sticky` element inside a scrolling document — so it cannot be
 * scrolled away even momentarily on a rubber-band overscroll.
 *
 * Its own parts are preferences too (spec 050): the breadcrumb trail and the
 * scope switcher can be hidden. The home link, the palette button, and the
 * layout controls cannot — they are how a user gets out of a layout they do
 * not like.
 */
export default function Masthead({
  pathname,
  breadcrumbs = true,
  scopeSwitcher = true,
  sidebarOpen,
  inspectorOpen,
  onToggleSidebar,
  onToggleInspector,
  onOpenPalette,
  layoutMenu,
  modulesMenu,
}: {
  pathname: string
  breadcrumbs?: boolean
  scopeSwitcher?: boolean
  sidebarOpen: boolean
  inspectorOpen: boolean
  onToggleSidebar: () => void
  onToggleInspector: () => void
  onOpenPalette: () => void
  /** The Layout menu, rendered beside the panel toggles. */
  layoutMenu?: ReactNode
  /**
   * The Modules menu, rendered before the breadcrumb trail. The shell passes
   * it only when the navigation rail is hidden (BL-20260905-08).
   */
  modulesMenu?: ReactNode
}) {
  const crumbs = breadcrumbsForPath(pathname)

  return (
    <header
      data-testid="masthead"
      className="flex h-[var(--shell-masthead-h)] shrink-0 items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-3 backdrop-blur sm:px-4"
      style={{ zIndex: 'var(--z-masthead)' }}
    >
      <Link
        href="/"
        aria-label="Law AI home"
        className="tap-target flex shrink-0 items-center gap-2 rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
      >
        {/* The mark stays 32px; the link around it is the 44px target. */}
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-sm font-bold text-white">
          LA
        </span>
        <span className="hidden text-lg font-semibold tracking-tight sm:inline">
          Law<span className="text-blue-400"> AI</span>
        </span>
      </Link>

      {modulesMenu}

      {/* Where am I. Hidden on the narrowest viewports, where the compact tab
       * bar already names the section and horizontal room is scarce. */}
      {breadcrumbs && (
      <nav aria-label="Breadcrumb" className="hidden min-w-0 flex-1 md:block">
        <ol className="flex items-center gap-1.5 text-xs text-slate-400">
          {crumbs.map((c) => (
            <li key={c.href} className="flex min-w-0 items-center gap-1.5">
              <span aria-hidden="true" className="text-slate-700">
                /
              </span>
              {c.current ? (
                <span aria-current="page" className="truncate text-slate-300">
                  {c.label}
                </span>
              ) : (
                <Link
                  href={c.href}
                  className="truncate transition hover:text-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
                >
                  {c.label}
                </Link>
              )}
            </li>
          ))}
        </ol>
      </nav>
      )}

      {/* Spacer so the control cluster stays right-aligned once the
       * breadcrumb trail is hidden — by the viewport or by preference. */}
      <div className={'min-w-0 flex-1' + (breadcrumbs ? ' md:hidden' : '')} />

      <div className="flex shrink-0 items-center gap-2">
        {scopeSwitcher && (
          <div className="hidden lg:block">
            <ScopeSwitcher />
          </div>
        )}

        {/* Who you are, next to what you are scoped to. Not a preference: a
         * user who cannot find the way back into their account cannot reach
         * their matters or share an analysis at all (BL-20260906-08). */}
        <AccountMenu />

        <button
          type="button"
          onClick={onOpenPalette}
          aria-label="Open command palette"
          className="tap-target flex items-center justify-center gap-2 rounded-md border border-slate-700 px-2.5 text-xs text-slate-400 transition hover:border-blue-500/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
        >
          <span aria-hidden="true">⌕</span>
          <kbd className="hidden font-mono text-[10px] text-slate-400 sm:inline">
            ⌘K
          </kbd>
        </button>

        {layoutMenu}

        <PanelToggle
          controls="shell-sidebar"
          open={sidebarOpen}
          onClick={onToggleSidebar}
          label="sidebar"
          hint="["
        />
        <PanelToggle
          controls="shell-inspector"
          open={inspectorOpen}
          onClick={onToggleInspector}
          label="inspector"
          hint="]"
        />
      </div>
    </header>
  )
}

function PanelToggle({
  controls,
  open,
  onClick,
  label,
  hint,
}: {
  controls: string
  open: boolean
  onClick: () => void
  label: string
  hint: string
}) {
  const name = `${open ? 'Collapse' : 'Expand'} ${label}`
  return (
    <button
      type="button"
      aria-pressed={open}
      aria-expanded={open}
      aria-controls={controls}
      aria-label={name}
      title={`${name} (${hint})`}
      onClick={onClick}
      className={
        'tap-target rounded-md border px-2.5 text-xs capitalize transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
        (open
          ? 'border-blue-500/40 bg-blue-600/10 text-blue-200'
          : 'border-slate-700 text-slate-400 hover:border-blue-500/40 hover:text-white')
      }
    >
      {label}
    </button>
  )
}
