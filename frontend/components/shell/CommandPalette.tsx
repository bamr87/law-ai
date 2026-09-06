'use client'

import { MODULE_CATALOG } from '@/lib/modules/catalog'
import {
  buildCommands,
  filterCommands,
  type ShellCommand,
} from '@/lib/shell/commands'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Scrim, useFocusTrap } from './Overlay'

/**
 * ⌘K palette over the module catalog and the shell's own layout actions
 * (BL-20260830-09).
 *
 * Generated from `MODULE_CATALOG`, never hand-listed: registering a module is
 * the only edit needed to make it reachable by keyboard.
 */
export default function CommandPalette({
  open,
  onClose,
  onAction,
}: {
  open: boolean
  onClose: () => void
  onAction: (action: NonNullable<ShellCommand['action']>) => void
}) {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLUListElement | null>(null)
  const ref = useFocusTrap<HTMLDivElement>(open, onClose)

  const all = useMemo(() => buildCommands(MODULE_CATALOG), [])
  const results = useMemo(() => filterCommands(all, query), [all, query])

  // Reopening a palette with the last search still in it is a papercut: the
  // user's first keystroke would append to a stale query.
  useEffect(() => {
    if (open) {
      setQuery('')
      setCursor(0)
      inputRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    setCursor(0)
  }, [query])

  useEffect(() => {
    const active = listRef.current?.querySelector('[data-active="true"]')
    // Guarded: jsdom and some embedded webviews ship no scrollIntoView, and a
    // palette that throws while you arrow through it is worse than one that
    // does not auto-scroll.
    if (active && typeof active.scrollIntoView === 'function') {
      active.scrollIntoView({ block: 'nearest' })
    }
  }, [cursor])

  if (!open) return null

  const run = (cmd: ShellCommand | undefined) => {
    if (!cmd) return
    onClose()
    if (cmd.href) router.push(cmd.href)
    else if (cmd.action) onAction(cmd.action)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (results.length ? (c + 1) % results.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) =>
        results.length ? (c - 1 + results.length) % results.length : 0,
      )
    } else if (e.key === 'Enter') {
      e.preventDefault()
      run(results[cursor])
    }
  }

  return (
    <>
      <Scrim onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-testid="command-palette"
        className="fixed left-1/2 top-[12vh] w-[min(36rem,92vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl outline-none"
        style={{ zIndex: 'var(--z-palette)' }}
      >
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls="command-palette-list"
          aria-activedescendant={
            results[cursor] ? `cmd-${results[cursor].id}` : undefined
          }
          aria-label="Search commands"
          placeholder="Jump to a module or run a layout command…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          className="w-full border-b border-slate-800 bg-transparent px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus-ring"
        />
        <ul
          ref={listRef}
          id="command-palette-list"
          role="listbox"
          aria-label="Commands"
          className="shell-panel-scroll max-h-[min(24rem,60vh)] py-1"
        >
          {results.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-slate-400">
              Nothing matches “{query}”.
            </li>
          )}
          {results.map((cmd, i) => {
            // Group headers are derived from the neighbour, not from a
            // counter mutated mid-render — a render-time reassignment gives
            // inconsistent output when React re-renders the list.
            const header =
              i === 0 || results[i - 1].group !== cmd.group ? cmd.group : null
            const active = i === cursor
            return (
              <li key={cmd.id}>
                {header && (
                  <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    {header}
                  </p>
                )}
                <button
                  type="button"
                  id={`cmd-${cmd.id}`}
                  role="option"
                  aria-selected={active}
                  data-active={active}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => run(cmd)}
                  className={
                    'flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition ' +
                    (active
                      ? 'bg-blue-600/20 text-blue-100'
                      : 'text-slate-300 hover:bg-slate-800/60')
                  }
                >
                  <span className="truncate">{cmd.label}</span>
                  {cmd.hint && (
                    <span className="shrink-0 font-mono text-[11px] text-slate-400">
                      {cmd.hint}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
        <p className="border-t border-slate-800 px-4 py-2 text-[11px] text-slate-400">
          <kbd className="font-mono">↑↓</kbd> move ·{' '}
          <kbd className="font-mono">↵</kbd> open ·{' '}
          <kbd className="font-mono">Esc</kbd> close
        </p>
      </div>
    </>
  )
}
