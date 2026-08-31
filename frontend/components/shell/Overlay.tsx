'use client'

import { useCallback, useEffect, useRef, type RefObject } from 'react'

/**
 * Shared behaviour for every layer that sits on top of the shell: mobile
 * drawers, the command palette, the shortcut sheet.
 *
 * Three things a hand-rolled overlay always forgets, and that a legal tool
 * used by keyboard and screen-reader users cannot afford to:
 *   - focus moves *into* the layer when it opens,
 *   - Tab cannot escape it while it is open,
 *   - focus goes back where it came from when it closes.
 */

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

export function useFocusTrap<T extends HTMLElement>(
  active: boolean,
  onDismiss: () => void,
): RefObject<T | null> {
  const ref = useRef<T | null>(null)
  const restoreTo = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!active) return
    const node = ref.current
    restoreTo.current =
      typeof document !== 'undefined'
        ? (document.activeElement as HTMLElement | null)
        : null

    const first = node?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? node)?.focus?.()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onDismiss()
        return
      }
      if (e.key !== 'Tab' || !node) return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const firstItem = items[0]
      const lastItem = items[items.length - 1]
      const activeEl = document.activeElement
      if (e.shiftKey && (activeEl === firstItem || activeEl === node)) {
        e.preventDefault()
        lastItem.focus()
      } else if (!e.shiftKey && activeEl === lastItem) {
        e.preventDefault()
        firstItem.focus()
      }
    }

    node?.addEventListener('keydown', onKeyDown)
    return () => {
      node?.removeEventListener('keydown', onKeyDown)
      // Only pull focus back if it is still inside the layer we are closing —
      // otherwise we would yank it away from whatever the user just clicked.
      if (!node || node.contains(document.activeElement)) {
        restoreTo.current?.focus?.()
      }
    }
  }, [active, onDismiss])

  return ref
}

/** Full-bleed dimmer. Clicking it dismisses; it is never a tab stop. */
export function Scrim({ onClick }: { onClick: () => void }) {
  return (
    <div
      data-testid="scrim"
      aria-hidden="true"
      onClick={onClick}
      className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm"
      style={{ zIndex: 'var(--z-scrim)' }}
    />
  )
}

/**
 * Off-canvas panel for viewports too narrow to hold a column. Same content as
 * the docked panel — a phone user gets the real sidebar, not a stub.
 */
export default function Drawer({
  open,
  side,
  label,
  onClose,
  children,
}: {
  open: boolean
  side: 'left' | 'right'
  label: string
  onClose: () => void
  children: React.ReactNode
}) {
  const dismiss = useCallback(() => onClose(), [onClose])
  const ref = useFocusTrap<HTMLDivElement>(open, dismiss)
  if (!open) return null

  return (
    <>
      <Scrim onClick={dismiss} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        data-testid={`drawer-${side}`}
        className={
          'shell-panel-scroll fixed bottom-0 top-[var(--shell-masthead-h)] w-[min(20rem,85vw)] border-slate-800 bg-slate-950 shadow-2xl outline-none ' +
          (side === 'left' ? 'left-0 border-r' : 'right-0 border-l')
        }
        style={{ zIndex: 'var(--z-drawer)' }}
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {label}
          </p>
          <button
            type="button"
            onClick={dismiss}
            className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </>
  )
}
