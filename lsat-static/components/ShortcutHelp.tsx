'use client'

import { useEffect, useRef } from 'react'

import { useModalBlock } from '@/lib/keyboard'

/**
 * The keyboard reference, opened with `?`.
 *
 * A shortcut nobody can discover is a shortcut nobody uses, so this is the
 * other half of the bindings themselves. Rendered as a modal dialog: focus
 * moves in on open, Tab is held inside while it is up, and Escape (or the
 * close button) returns focus to whatever opened it.
 */

type Group = { title: string; rows: [string, string][] }

const GROUPS: Group[] = [
  {
    title: 'Anywhere',
    rows: [
      ['?', 'Show or hide this reference'],
      ['[  /  ]', 'Previous / next section'],
      ['.', 'Keep the header visible, or let it hide on scroll'],
      ['Esc', 'Close this reference'],
    ],
  },
  {
    title: 'Logical Reasoning · Reading Comprehension · Logic Games',
    rows: [
      ['A – E', 'Select that answer choice'],
      ['↑ ↓ ← →', 'Move between choices (when a choice has focus)'],
      ['Home  /  End', 'First / last choice (when a choice has focus)'],
      ['Enter', 'Check the answer — then again to advance'],
      ['N  /  P', 'Next / previous question (answers you gave are kept)'],
      ['H', 'Reveal the next hint'],
      ['J  /  K', 'Move back / forward through revealed hints'],
      ['R', 'Reveal the final step (after checking)'],
    ],
  },
  {
    title: 'Knowledge library',
    rows: [
      ['/', 'Jump to the library search box'],
      ['J  /  K', 'Next / previous article in the visible list'],
      ['Esc', 'Leave the search box'],
    ],
  },
  {
    title: 'Argumentative Writing',
    rows: [
      ['O', 'Open the first prompt, and jump into the editor'],
      ['T', 'Start or pause the writing clock'],
      ['Ctrl / ⌘ + Enter', 'Submit the draft and unlock feedback'],
      ['M', 'Show or hide the model response'],
      ['Esc', 'Leave the editor, then back to all prompts'],
      ['O', 'Return to the editor after Esc'],
    ],
  },
]

export default function ShortcutHelp({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)
  const openerRef = useRef<Element | null>(null)

  useModalBlock()

  useEffect(() => {
    openerRef.current = document.activeElement
    closeRef.current?.focus()
    const opener = openerRef.current
    return () => {
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [])

  // Hold Tab inside the dialog. Without this, tabbing walks the page behind
  // the scrim, which for a screen-reader user is indistinguishable from the
  // dialog having closed.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="scrim" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-help-title"
        className="shortcut-help"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shortcut-help-head">
          <h2 id="shortcut-help-title">Keyboard shortcuts</h2>
          <button
            ref={closeRef}
            type="button"
            className="btn"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
          >
            Close
          </button>
        </div>
        <p className="drill-timing">
          Every step of a drill can be driven from the keyboard. Shortcuts never
          fire while you are typing — the writing editor keeps every keystroke.
        </p>
        {GROUPS.map((g) => (
          <section key={g.title} className="shortcut-group">
            <h3>{g.title}</h3>
            <dl className="shortcut-list">
              {/* Keyed by position, not by the key cap: a group may legitimately
                  document the same cap twice (O opens a prompt and returns to
                  the editor), and `key={keys}` made React collide the two rows
                  (BL-20260906-62). */}
              {g.rows.map(([keys, what], i) => (
                <div key={`${g.title}-${i}`} className="shortcut-row">
                  <dt>
                    <kbd>{keys}</kbd>
                  </dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </div>
  )
}
