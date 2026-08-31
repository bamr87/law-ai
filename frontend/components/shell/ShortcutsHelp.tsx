'use client'

import { SHORTCUT_HELP } from '@/lib/shell/shortcuts'
import { Scrim, useFocusTrap } from './Overlay'

/** `?` sheet. A keyboard contract nobody can discover is not a contract. */
export default function ShortcutsHelp({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const ref = useFocusTrap<HTMLDivElement>(open, onClose)
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
        <dl className="mt-4 space-y-2">
          {SHORTCUT_HELP.map((s) => (
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
        <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
          Shortcuts stay out of the way while you are typing — a bare key never
          fires from inside a text field.
        </p>
      </div>
    </>
  )
}
