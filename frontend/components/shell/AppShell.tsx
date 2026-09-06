'use client'

import LegalDisclaimerFooter from '@/components/LegalDisclaimer'
import { moduleForPath } from '@/lib/modules/catalog'
import {
  backToTopVisible,
  breadcrumbsVisible,
  inspectorDefaultOpen,
  inspectorSide,
  railVisible,
  scopeSwitcherVisible,
  sidebarDefaultOpen,
  sidebarSide,
  type Dock as DockName,
  type PanelSide,
} from '@/lib/settings/catalog'
import { resetLayout, resolvePanelSides } from '@/lib/shell/layout'
import {
  panelHref,
  panelOpen,
  withoutPanels,
  withPanel,
  type PanelKey,
} from '@/lib/shell/panels'
import {
  isTypingTarget,
  matchShortcut,
  type ShortcutGroup,
} from '@/lib/shell/shortcuts'
import type { ShellCommand } from '@/lib/shell/commands'
import type { SettingValue } from '@/lib/scope/types'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import BackToTop from './BackToTop'
import CommandPalette from './CommandPalette'
import DockZone from './DockZone'
import ModulesMenu from './ModulesMenu'
import LayoutMenu from './LayoutMenu'
import Masthead from './Masthead'
import MobileTabBar from './MobileTabBar'
import NavRail from './NavRail'
import Drawer from './Overlay'
import { PageShortcutsProvider, type ShortcutRegistry } from './PageShortcuts'
import { SettingsSnapshotProvider } from './SettingsSnapshot'
import { ShellScrollProvider, useMainScrollController } from './ShellScroll'
import ShortcutsHelp from './ShortcutsHelp'
import { COMPACT_QUERY, NARROW_QUERY, useMediaQuery } from './useMediaQuery'
import { useSetting } from './useSetting'

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
 *
 * What the shell shows, and where, is the user's to choose (spec 050): every
 * part of the chrome except the UPL disclaimer has a preference behind it,
 * edited from the masthead's Layout menu, the palette, or `/settings`. The
 * shell reads them through `useSetting` and stays a plain composition — it
 * never learns what a module is, and it never hides a running clock.
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

  // Shortcut rows contributed by whatever page is on screen (BL-20260901-10).
  // Refcounted by title: an RC passage stacks several question cards, and the
  // first to unmount must not take the group away from the rest.
  const [pageShortcuts, setPageShortcuts] = useState<ShortcutGroup[]>([])
  const shortcutCounts = useRef<Map<string, number>>(new Map())
  const shortcutRegistry = useMemo<ShortcutRegistry>(
    () => ({
      register: (group) => {
        const n = (shortcutCounts.current.get(group.title) ?? 0) + 1
        shortcutCounts.current.set(group.title, n)
        if (n > 1) return
        setPageShortcuts((prev) =>
          prev.some((g) => g.title === group.title) ? prev : [...prev, group],
        )
      },
      unregister: (title) => {
        const n = (shortcutCounts.current.get(title) ?? 1) - 1
        if (n > 0) {
          shortcutCounts.current.set(title, n)
          return
        }
        shortcutCounts.current.delete(title)
        setPageShortcuts((prev) => prev.filter((g) => g.title !== title))
      },
    }),
    [],
  )

  // Layout preferences. `useSetting` reads through useSyncExternalStore, so
  // these are hydration-safe: the server render sees the defaults and the
  // stored choice applies right after mount.
  const [railShown, setRailShown] = useSetting(railVisible)
  const [crumbsShown, setCrumbsShown] = useSetting(breadcrumbsVisible)
  const [scopeShown] = useSetting(scopeSwitcherVisible)
  const [topShown] = useSetting(backToTopVisible)
  const [sideOfSidebar] = useSetting(sidebarSide)
  const [sideOfInspector] = useSetting(inspectorSide)
  const [sidebarPreferred, setSidebarPreferred] = useSetting(sidebarDefaultOpen)
  const [inspectorPreferred, setInspectorPreferred, inspectorPref] =
    useSetting(inspectorDefaultOpen)

  // Defaults are viewport-aware: an auto-opened drawer covering the content on
  // first paint is how a phone user learns to distrust the app. An explicit
  // `?sidebar=1` still wins, so a shared link opens the layout it promised.
  //
  // For the inspector, a stored preference is the user's explicit choice and
  // beats the UPL-route auto-open; with nothing stored, a UPL route opens it
  // so the disclaimer is on screen (spec 040 FR-2). The footer disclaimer
  // inside <main> stays either way — that one has no preference.
  const inspectorChosen = inspectorPref.source !== 'default'
  const sidebarOpen = panelOpen(params, 'sidebar', !compact && sidebarPreferred)
  const inspectorOpen = panelOpen(
    params,
    'inspector',
    !narrow && (inspectorChosen ? inspectorPreferred : mod.upl),
  )

  const setPanel = useCallback(
    (key: PanelKey, open: boolean) => {
      // The URL carries this page's layout — linkable, restored by Back — and
      // the preference carries it to the next page, so a collapsed panel stays
      // collapsed across a navigation instead of springing back.
      if (key === 'sidebar') setSidebarPreferred(open)
      else setInspectorPreferred(open)
      router.replace(panelHref(pathname, withPanel(params, key, open)), {
        scroll: false,
      })
    },
    [params, pathname, router, setInspectorPreferred, setSidebarPreferred],
  )

  const toggleSidebar = useCallback(
    () => setPanel('sidebar', !sidebarOpen),
    [setPanel, sidebarOpen],
  )
  const toggleInspector = useCallback(
    () => setPanel('inspector', !inspectorOpen),
    [setPanel, inspectorOpen],
  )

  const resetAll = useCallback(() => {
    resetLayout()
    // The URL's panel params are layout too: a reset that left `?sidebar=0`
    // behind would look as if it had not worked.
    router.replace(panelHref(pathname, withoutPanels(params)), {
      scroll: false,
    })
  }, [params, pathname, router])

  const runCommand = useCallback(
    (action: NonNullable<ShellCommand['action']>) => {
      if (action === 'toggle-sidebar') toggleSidebar()
      else if (action === 'toggle-inspector') toggleInspector()
      else if (action === 'toggle-rail') setRailShown(!railShown)
      else if (action === 'toggle-breadcrumbs') setCrumbsShown(!crumbsShown)
      else if (action === 'reset-layout') resetAll()
      else if (action === 'toggle-help') setHelpOpen((v) => !v)
      else if (action === 'back-to-top') scroll.scrollToTop()
    },
    [
      crumbsShown,
      railShown,
      resetAll,
      scroll,
      setCrumbsShown,
      setRailShown,
      toggleInspector,
      toggleSidebar,
    ],
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

  const sidebarDocked = sidebarOpen && !compact
  const sidebarDrawer = sidebarOpen && compact
  const inspectorDocked = inspectorOpen && !narrow
  const inspectorDrawer = inspectorOpen && narrow

  const zone = (dock: DockName) => (
    <div className="border-b border-slate-800 p-3">
      <DockZone dock={dock} pathname={pathname} openDocks={openDocks} />
    </div>
  )

  // Which edge each panel docks to is a preference; the order on an edge is
  // not (`resolvePanelSides`). The shell just maps the result.
  const arrangement = resolvePanelSides({
    sidebar: sideOfSidebar,
    inspector: sideOfInspector,
  })
  const docked = (key: PanelKey, side: PanelSide) => {
    if (key === 'sidebar') {
      if (!sidebarDocked) return null
      return (
        <DockedPanel
          key="sidebar"
          id="shell-sidebar"
          label="Contextual navigation"
          side={side}
          width="w-[var(--shell-sidebar-w)]"
          from="md:block"
          tint="bg-slate-950/60"
        >
          {zone('sidebar')}
          {sidebar}
        </DockedPanel>
      )
    }
    if (!inspectorDocked) return null
    return (
      <DockedPanel
        key="inspector"
        id="shell-inspector"
        label="Inspector"
        side={side}
        width="w-[var(--shell-inspector-w)]"
        from="lg:block"
        tint="bg-slate-950/80"
      >
        {zone('inspector')}
        {inspector}
      </DockedPanel>
    )
  }

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
          breadcrumbs={crumbsShown}
          scopeSwitcher={scopeShown}
          sidebarOpen={sidebarOpen}
          inspectorOpen={inspectorOpen}
          onToggleSidebar={toggleSidebar}
          onToggleInspector={toggleInspector}
          onOpenPalette={() => setPaletteOpen(true)}
          // With the rail hidden, a mouse user who does not know ⌘K would be
          // left navigating by the (also hideable) breadcrumb trail alone.
          modulesMenu={
            !railShown ? <ModulesMenu pathname={pathname} /> : undefined
          }
          layoutMenu={
            <LayoutMenu
              pathname={pathname}
              sidebarOpen={sidebarOpen}
              inspectorOpen={inspectorOpen}
              onToggleSidebar={toggleSidebar}
              onToggleInspector={toggleInspector}
              onReset={resetAll}
            />
          }
        />

        <div className="flex min-h-0 flex-1">
          {railShown && <NavRail pathname={pathname} />}

          {arrangement.left.map((key) => docked(key, 'left'))}

          {/* `relative` so the back-to-top affordance can anchor to the
           * viewport-sized region rather than riding the scrolled content. */}
          <div className="relative flex min-w-0 flex-1 flex-col">
            <main
              id="main"
              ref={mainRef}
              tabIndex={-1}
              className="shell-scroll min-h-0 flex-1 outline-none"
            >
              <PageShortcutsProvider registry={shortcutRegistry}>
                {children}
              </PageShortcutsProvider>
              <LegalDisclaimerFooter />
            </main>
            {topShown && <BackToTop />}
          </div>

          {arrangement.right.map((key) => docked(key, 'right'))}
        </div>

        <MobileTabBar pathname={pathname} />

        <Drawer
          open={sidebarDrawer}
          side={sideOfSidebar}
          label="Contextual navigation"
          onClose={() => setPanel('sidebar', false)}
        >
          {zone('sidebar')}
          {sidebar}
        </Drawer>
        <Drawer
          open={inspectorDrawer}
          side={sideOfInspector}
          label="Inspector"
          onClose={() => setPanel('inspector', false)}
        >
          {zone('inspector')}
          {inspector}
        </Drawer>

        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onAction={runCommand}
        />
        <ShortcutsHelp
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          pageGroups={pageShortcuts}
        />
      </div>
    </ShellScrollProvider>
  )
}

/**
 * A docked side column. Which edge it sits on decides only its border; the
 * breakpoint it appears from (`md` for the sidebar, `lg` for the inspector)
 * and its width stay with the panel, whichever edge it is moved to.
 */
function DockedPanel({
  id,
  label,
  side,
  width,
  from,
  tint,
  children,
}: {
  id: string
  label: string
  side: PanelSide
  width: string
  from: string
  tint: string
  children: ReactNode
}) {
  return (
    <aside
      id={id}
      data-side={side}
      aria-label={label}
      className={`hidden shrink-0 border-slate-800 ${width} ${from} ${tint} ${
        side === 'left' ? 'border-r' : 'border-l'
      }`}
    >
      {children}
    </aside>
  )
}

export default function AppShell({
  initialSettings,
  initialUserScopeId,
  ...props
}: {
  children: ReactNode
  sidebar: ReactNode
  inspector: ReactNode
  /**
   * The setting rows the server rendered with, read from the mirrored cookie
   * in `app/(app)/layout.tsx`. They are the hydration snapshot too, so a
   * chosen layout is on the first paint instead of reflowing after mount
   * (BL-20260905-09).
   */
  initialSettings?: SettingValue[]
  /**
   * The scope those rows were written at, from the mirrored scope cookie. A
   * layout row lives at `user:<pk>` once someone is signed in, so the server
   * needs the id to resolve the same chain the client does (BL-20260905-10).
   */
  initialUserScopeId?: string | null
}) {
  return (
    <SettingsSnapshotProvider
      rows={initialSettings}
      userScopeId={initialUserScopeId}
    >
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
    </SettingsSnapshotProvider>
  )
}
