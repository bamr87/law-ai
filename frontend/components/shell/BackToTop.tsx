'use client'

import { useShellScroll } from './ShellScroll'

/** Appears once the reader is far enough down that Home is a real trip. */
const SHOW_AFTER = 480

export default function BackToTop() {
  const { scrollTop, scrollToTop } = useShellScroll()
  if (scrollTop < SHOW_AFTER) return null

  return (
    <button
      type="button"
      onClick={scrollToTop}
      data-testid="back-to-top"
      className="shell-motion absolute bottom-5 right-5 rounded-full border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs text-slate-300 shadow-lg backdrop-blur transition hover:border-blue-500/50 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
      style={{ zIndex: 'var(--z-sticky-sub)' }}
    >
      <span aria-hidden="true">↑</span> Top
    </button>
  )
}
