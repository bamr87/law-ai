/**
 * The two page-level bindings (BL-20260901-07).
 *
 * `[` / `]` move between sections and `Escape` closes the shortcut sheet.
 * Both were verified only by pressing keys in a browser by hand, and both are
 * advertised to the reader in `ShortcutHelp` — a binding the sheet documents
 * and nothing exercises is a promise with no test behind it.
 *
 * Two regressions are pinned here in particular:
 *
 *  1. Section movement is deliberately `[` / `]` rather than the arrows, so
 *     the answer radiogroup keeps the arrows for choosing between choices; and
 *     it clamps at both ends rather than wrapping.
 *  2. `Escape` is bound **only while the sheet is open** (`app/page.tsx`).
 *     Claiming it unconditionally would swallow it from everything else that
 *     wants it — the writing editor uses Escape to leave the text field — so
 *     the last case asserts the key is left alone while the sheet is closed.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

/** The accessible name of the destination the nav marks as current. */
function currentSection(): string {
  const active = document.querySelector('[aria-current="page"]')
  return active?.getAttribute('aria-label') ?? '(none)'
}

function press(key: string): void {
  fireEvent.keyDown(window, { key })
}

describe('section movement with [ and ]', () => {
  it('steps forward and back through the nav', () => {
    render(<Page />)
    expect(currentSection()).toBe('Overview')

    press(']')
    expect(currentSection()).toBe('Logical Reasoning')
    press(']')
    expect(currentSection()).toBe('Reading Comprehension')

    press('[')
    expect(currentSection()).toBe('Logical Reasoning')
    press('[')
    expect(currentSection()).toBe('Overview')
  })

  it('clamps at both ends rather than wrapping around', () => {
    render(<Page />)
    // Already on the first destination: `[` has nowhere to go.
    press('[')
    expect(currentSection()).toBe('Overview')

    // Walk past the last destination; NAV has seven entries.
    for (let i = 0; i < 10; i += 1) press(']')
    expect(currentSection()).toBe('Stats')
  })

  it('is suspended while the shortcut sheet is open', () => {
    render(<Page />)
    press('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Everything behind a modal is inert; only the sheet's own keys run.
    press(']')
    expect(currentSection()).toBe('Overview')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('the shortcut sheet', () => {
  it('closes with Escape', () => {
    render(<Page />)
    press('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    press('Escape')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes with ? again', () => {
    render(<Page />)
    press('?')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    press('?')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('leaves Escape alone while it is closed', () => {
    render(<Page />)
    const escape = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    })
    window.dispatchEvent(escape)
    // `useShortcuts` calls preventDefault before dispatching, so a page-level
    // Escape binding that was not conditional on the sheet being open would
    // show up here — and would take the key away from the writing editor.
    expect(escape.defaultPrevented).toBe(false)
  })
})
