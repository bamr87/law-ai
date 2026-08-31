'use client'

import LegalDisclaimerFooter from '@/components/LegalDisclaimer'
import { moduleForPath } from '@/lib/modules/catalog'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { resolveEffective } from '@/lib/scope/resolver'
import { listSettingValues } from '@/lib/scope/store'
import { inspectorDefaultOpen } from '@/lib/settings/catalog'
import {
  panelHref,
  panelOpen,
  withPanel,
  type PanelKey,
} from '@/lib/shell/panels'
import { isTypingTarget, matchShortcut } from '@/lib/shell/shortcuts'
import type { ShellCommand } from '@/lib/shell/commands'
import type { Dock as DockName } from '@/lib/settings/catalog'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import BackToTop from './BackToTop'
import DockZone from './DockZone'
import CommandPalette from './CommandPalette'
import Masthead from './Masthead'
import MobileTabBar from './MobileTabBar'
import NavRail from './NavRail'
import Drawer from './Overlay'
import { ShellScrollProvider, useMainScrollController } from './ShellScroll'
import ShortcutsHelp from './ShortcutsHelp'
import { COMPACT_QUERY, NARROW_QUERY, useMediaQuery } from './useMediaQuery'

/**
 * The application shell.
 *
 * The load-bearing decision here is that **the viewport does not scroll**.
 * The outer element is `h-dvh overflow-hidden`, so the masthead, nav rail,
 * contextual sidebar, inspector, and compact tab bar are structurally
 * incapable of scrolling out of view — they are flex children of a row that
 * is exactly as tall as the screen. Exactly one element scrolls page content
 * (`<main class="shell-scroll">`), and panels that need it scroll themselves.
 *
 * `h-dvh` rather than `h-screen`: on mobile Safari/Chrome `100vh` is the
 * *expanded* viewport, so a `h-screen` shell hides its bottom bar behind the
 * browser's own chrome until the user scrolls.
 *
 * Panels are URL state (`?sidebar=0&inspector=1`) so a layout is linkable and
 * Back restores it. Below `md` they become focus-trapped drawers instead of
 * columns, because a 320px viewport has no room for three of them.
 */
function ShellInner({
  children,
  sidebar,
  inspector,
}: {
  children: ReactNode
  sidebar: ReactNode
  inspector: ReactNode
}) {
  const pathname = usePathname() || '/'
  const params = useSearchParams()
  const router = useRouter()
  const mod = moduleForPath(pathname)

  const compact = useMediaQuery(COMPACT_QUERY)
  const narrow = useMediaQuery(NARROW_QUERY)

  const { state: scroll, mainRef } = useMainScrollController(pathname)

  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  // ui.inspector.default_open (spec 040 FR-2): read after mount — the store is
  // localStorage-backed, so reading during render would break hydration.
  const [inspectorPreferred, setInspectorPreferred] = useState(false)
  useEffect(() => {
    setInspectorPreferred(
      resolveEffective(
        inspectorDefaultOpen,
        [INSTANCE_SCOPE],
        listSettingValues(),
        false,
      ).value,
    )
  }, [])

  // Defaults are viewport-aware: an auto-opened drawer covering the content on
  // first paint is how a phone user learns to distrust the app. An explicit
  // `?sidebar=1` still wins, so a shared link opens the layout it promised.
  const sidebarOpen = panelOpen(params, 'sidebar', !compact)
  const inspectorOpen = panelOpen(
    params,
    'inspector',
    !narrow && (mod.upl || inspectorPreferred),
  )

  const setPanel = useCallback(
    (key: PanelKey, open: boolean) => {
      router.replace(panelHref(pathname, withPanel(params, key, open)), {
        scroll: false,
      })
    },
    [params, pathname, router],
  )

  const toggleSidebar = useCallback(
    () => setPanel('sidebar', !sidebarOpen),
    [setPanel, sidebarOpen],
  )
  const toggleInspector = useCallback(
    () => setPanel('inspector', !inspectorOpen),
    [setPanel, inspectorOpen],
  )

  const runCommand = useCallback(
    (action: NonNullable<ShellCommand['action']>) => {
      if (action === 'toggle-sidebar') toggleSidebar()
      else if (action === 'toggle-inspector') toggleInspector()
      else if (action === 'toggle-help') setHelpOpen((v) => !v)
      else if (action === 'back-to-top') scroll.scrollToTop()
    },
    [scroll, toggleInspector, toggleSidebar],
  )

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const action = matchShortcut(e, { typing: isTypingTarget(e.target) })
      if (!action) return
      if (action === 'dismiss') {
        // Overlays trap and stop their own Escape; this only catches the case
        // where one is open but focus has drifted outside it.
        if (paletteOpen || helpOpen) {
          setPaletteOpen(false)
          setHelpOpen(false)
        }
        return
      }
      e.preventDefault()
      if (action === 'open-palette') setPaletteOpen(true)
      else if (action === 'toggle-sidebar') toggleSidebar()
      else if (action === 'toggle-inspector') toggleInspector()
      else if (action === 'toggle-help') setHelpOpen((v) => !v)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [helpOpen, paletteOpen, toggleInspector, toggleSidebar])

  // Which dock zones are actually on screen. A widget whose preferred panel is
  // collapsed falls back to one that is open rather than vanishing.
  const openDocks: DockName[] = [
    ...(sidebarOpen ? (['sidebar'] as const) : []),
    ...(inspectorOpen ? (['inspector'] as const) : []),
  ]
  const onLsatRoute = pathname.startsWith('/lsat')

  const sidebarDocked = sidebarOpen && !compact
  const sidebarDrawer = sidebarOpen && compact
  const inspectorDocked = inspectorOpen && !narrow
  const inspectorDrawer = inspectorOpen && narrow

  return (
    <ShellScrollProvider value={scroll}>
      <div className="flex h-dvh flex-col overflow-hidden">
        {/* Above the masthead when focused — a skip link that lands *behind*
         * the chrome is a skip link nobody can see they have. */}
        <a
          href="#main"
          style={{ zIndex: 'var(--z-drawer)' }}
          className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded-md focus:bg-blue-600 focus:px-3 focus:py-2 focus:text-white"
        >
          Skip to main content
        </a>

        <Masthead
          pathname={pathname}
          sidebarOpen={sidebarOpen}
          inspectorOpen={inspectorOpen}
          onToggleSidebar={toggleSidebar}
          onToggleInspector={toggleInspector}
          onOpenPalette={() => setPaletteOpen(true)}
        />

        <div className="flex min-h-0 flex-1">
          <NavRail pathname={pathname} />

          {sidebarDocked && (
            <aside
              id="shell-sidebar"
              className="hidden w-[var(--shell-sidebar-w)] shrink-0 border-r border-slate-800 bg-slate-950/60 md:block"
              aria-label="Contextual navigation"
            >
              <div className="border-b border-slate-800 p-3">
                <DockZone
                  dock="sidebar"
                  onOwnRoute={onLsatRoute}
                  openDocks={openDocks}
                />
              </div>
              {sidebar}
            </aside>
          )}

          {/* `relative` so the back-to-top affordance can anchor to the
           * viewport-sized region rather than riding the scrolled content. */}
          <div className="relative flex min-w-0 flex-1 flex-col">
            <main
              id="main"
              ref={mainRef}
              tabIndex={-1}
              className="shell-scroll min-h-0 flex-1 outline-none"
            >
              {children}
              <LegalDisclaimerFooter />
            </main>
            <BackToTop />
          </div>

          {inspectorDocked && (
            <aside
              id="shell-inspector"
              className="hidden w-[var(--shell-inspector-w)] shrink-0 border-l border-slate-800 bg-slate-950/80 lg:block"
              aria-label="Inspector"
            >
              <div className="border-b border-slate-800 p-3">
                <DockZone
                  dock="inspector"
                  onOwnRoute={onLsatRoute}
                  openDocks={openDocks}
                />
              </div>
              {inspector}
            </aside>
          )}
        </div>

        <MobileTabBar pathname={pathname} />

        <Drawer
          open={sidebarDrawer}
          side="left"
          label="Contextual navigation"
          onClose={() => setPanel('sidebar', false)}
        >
          <div className="border-b border-slate-800 p-3">
            <DockZone
              dock="sidebar"
              onOwnRoute={onLsatRoute}
              openDocks={openDocks}
            />
          </div>
          {sidebar}
        </Drawer>
        <Drawer
          open={inspectorDrawer}
          side="right"
          label="Inspector"
          onClose={() => setPanel('inspector', false)}
        >
          <div className="border-b border-slate-800 p-3">
            <DockZone
              dock="inspector"
              onOwnRoute={onLsatRoute}
              openDocks={openDocks}
            />
          </div>
          {inspector}
        </Drawer>

        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onAction={runCommand}
        />
        <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      </div>
    </ShellScrollProvider>
  )
}

export default function AppShell(props: {
  children: ReactNode
  sidebar: ReactNode
  inspector: ReactNode
}) {
  return (
    <Suspense
      fallback={
        <div className="flex h-dvh flex-col overflow-hidden">
          <div className="h-[var(--shell-masthead-h)] shrink-0 border-b border-slate-800" />
          <div className="flex min-h-0 flex-1">
            <div className="hidden w-[var(--shell-rail-w)] shrink-0 border-r border-slate-800 md:block" />
            <div className="min-w-0 flex-1" />
          </div>
        </div>
      }
    >
      <ShellInner {...props} />
    </Suspense>
  )
}
