'use client'

import {
  mergeShortcutGroups,
  type ShortcutGroup,
} from '@/lib/shell/shortcuts'
import { Scrim, useFocusTrap } from './Overlay'

/**
 * `?` sheet. A keyboard contract nobody can discover is not a contract.
 *
 * The shell's own keys come first, then the groups the page on screen
 * registered through `usePageShortcuts` (BL-20260901-10) — so the LSAT drill's
 * A–E / Enter / N are findable from the same place as ⌘K, instead of only
 * from the card's own hint line.
 */
export default function ShortcutsHelp({
  open,
  onClose,
  pageGroups = [],
}: {
  open: boolean
  onClose: () => void
  /** Groups registered by the page currently on screen. */
  pageGroups?: ReadonlyArray<ShortcutGroup>
}) {
  const ref = useFocusTrap<HTMLDivElement>(open, onClose)
  const groups = mergeShortcutGroups(pageGroups)
  if (!open) return null

  return (
    <>
      <Scrim onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-heading"
        data-testid="shortcuts-help"
        className="fixed left-1/2 top-1/2 w-[min(28rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl outline-none"
        style={{ zIndex: 'var(--z-palette)' }}
      >
        <div className="flex items-start justify-between gap-4">
          <h2
            id="shortcuts-heading"
            className="text-sm font-semibold text-slate-100"
          >
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
          >
            Close
          </button>
        </div>
        <div className="shell-panel-scroll mt-4 max-h-[60vh] space-y-4">
          {groups.map((group) => (
            <section key={group.title} aria-labelledby={`shortcuts-${slug(group.title)}`}>
              <h3
                id={`shortcuts-${slug(group.title)}`}
                className="pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400"
              >
                {group.title}
              </h3>
              <dl className="space-y-2">
                {group.rows.map((s) => (
                  <div
                    key={s.keys}
                    className="flex items-center justify-between gap-4"
                  >
                    <dt className="text-sm text-slate-300">{s.label}</dt>
                    <dd>
                      <kbd className="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                        {s.keys}
                      </kbd>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <p className="mt-4 text-[11px] leading-relaxed text-slate-400">
          Shortcuts stay out of the way while you are typing — a bare key never
          fires from inside a text field.
        </p>
      </div>
    </>
  )
}

/** Stable id fragment for a group heading. */
function slug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}
