'use client'

import Link from 'next/link'
import ScopeSwitcher from './ScopeSwitcher'

export default function Masthead({
  sidebarOpen,
  inspectorOpen,
  onToggleSidebar,
  onToggleInspector,
}: {
  sidebarOpen: boolean
  inspectorOpen: boolean
  onToggleSidebar: () => void
  onToggleInspector: () => void
}) {
  return (
    <header className="sticky top-0 z-40 grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-slate-800 bg-slate-950/80 px-3 py-2 backdrop-blur sm:px-4">
      <Link href="/" className="flex items-center gap-2 justify-self-start">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-sm font-bold text-white">
          LA
        </span>
        <span className="text-lg font-semibold tracking-tight">
          Law<span className="text-blue-400"> AI</span>
        </span>
      </Link>
      <ScopeSwitcher />
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          aria-pressed={sidebarOpen}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          onClick={onToggleSidebar}
          className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-blue-500/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
        >
          Sidebar
        </button>
        <button
          type="button"
          aria-pressed={inspectorOpen}
          aria-label={inspectorOpen ? 'Collapse inspector' : 'Expand inspector'}
          onClick={onToggleInspector}
          className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-blue-500/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
        >
          Inspector
        </button>
      </div>
    </header>
  )
}
