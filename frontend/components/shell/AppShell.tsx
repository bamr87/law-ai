'use client'

import { moduleForPath } from '@/lib/modules/catalog'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { resolveEffective } from '@/lib/scope/resolver'
import { listSettingValues } from '@/lib/scope/store'
import { inspectorDefaultOpen } from '@/lib/settings/catalog'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useState, type ReactNode } from 'react'
import Masthead from './Masthead'
import NavRail from './NavRail'

function panelOpen(
  params: URLSearchParams,
  key: string,
  fallback: boolean,
): boolean {
  const v = params.get(key)
  if (v === '0') return false
  if (v === '1') return true
  return fallback
}

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
  const sidebarOpen = panelOpen(params, 'sidebar', true)
  const inspectorOpen = panelOpen(
    params,
    'inspector',
    mod.upl || inspectorPreferred,
  )

  function setPanel(key: 'sidebar' | 'inspector', open: boolean) {
    const next = new URLSearchParams(params.toString())
    next.set(key, open ? '1' : '0')
    const qs = next.toString()
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
  }

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-md focus:bg-blue-600 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <Masthead
        sidebarOpen={sidebarOpen}
        inspectorOpen={inspectorOpen}
        onToggleSidebar={() => setPanel('sidebar', !sidebarOpen)}
        onToggleInspector={() => setPanel('inspector', !inspectorOpen)}
      />
      <div className="flex min-h-0 flex-1">
        <NavRail pathname={pathname} />
        {sidebarOpen && (
          <aside
            className="hidden w-56 shrink-0 border-r border-slate-800 bg-slate-950/60 md:block"
            aria-label="Contextual navigation"
          >
            {sidebar}
          </aside>
        )}
        <main id="main" className="min-w-0 flex-1 overflow-auto">
          {children}
        </main>
        {inspectorOpen && (
          <aside
            className="hidden w-72 shrink-0 border-l border-slate-800 bg-slate-950/80 lg:block"
            aria-label="Inspector"
          >
            {inspector}
          </aside>
        )}
      </div>
    </div>
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
        <div className="flex min-h-screen flex-col">
          <div className="h-14 border-b border-slate-800" />
          <div className="flex-1" />
        </div>
      }
    >
      <ShellInner {...props} />
    </Suspense>
  )
}
