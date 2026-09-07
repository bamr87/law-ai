/**
 * Where focus lands, and what a screen reader hears (BL-20260901-11).
 *
 * Four fixes came out of a browser keyboard pass, and until this file existed
 * they were pinned only by `.read_text()` source assertions in
 * `tests/test_lsat_site.py::TestKeyboardContract` — which check that the code
 * *says* the right thing, not that focus *goes* the right place. Each one is a
 * rule about focus or announced state, which is what actually failed; the key
 * bindings themselves were fine (those are covered in keyboard.test.tsx).
 *
 *   1. A graded choice is `aria-disabled`, not `disabled`, so checking an
 *      answer does not throw focus to <body>.
 *   2. Paging back with `P` shows the answer you gave and the time you took.
 *   3. `N`/`P` land focus on the new question and announce the new position.
 *   4. `O` reaches the essay editor, not a card six Tab stops away from it.
 *
 * Cases 3 and 4 render the real page, because the live region and the section
 * switch both live there — asserting them against `Drill` alone would prove
 * the callback fires, not that anybody hears it.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Drill from '@/components/Drill'
import Page from '@/app/page'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return {
    ...actual,
    // Three short LR questions and one writing prompt, so the assertions are
    // about focus rather than about whatever the bank happens to hold today.
    questionsFor: () => f.QUESTIONS,
    passageById: () => undefined,
    guideFor: () => undefined,
    writingPrompts: [f.PROMPT],
    rubricFor: () => f.RUBRIC,
  }
})

function radios(): HTMLElement[] {
  return within(
    screen.getByRole('radiogroup', { name: 'Answer choices' }),
  ).getAllByRole('radio')
}

function card(): HTMLElement {
  return screen.getByRole('article')
}

describe('graded choices stay in the focus order', () => {
  it('keeps focus on the choice you checked, and marks every choice aria-disabled', () => {
    // `disabled` drops the element out of the focus order, so checking an
    // answer while the chosen choice had focus threw focus to <body>: no ring
    // to see, no position for a screen reader, and Tab restarting at the skip
    // link.
    render(<Drill section="LR" />)
    const c = radios()[2]
    c.focus()
    fireEvent.keyDown(c, { key: ' ' })
    fireEvent.keyDown(c, { key: 'Enter' })

    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
    expect(document.activeElement).toBe(radios()[2])
    expect(document.activeElement).not.toBe(document.body)
    for (const r of radios()) {
      expect(r).toHaveAttribute('aria-disabled', 'true')
      expect(r).not.toBeDisabled()
    }
    // Still reachable afterwards — a graded choice is readable, not removed.
    radios()[4].focus()
    expect(document.activeElement).toBe(radios()[4])
  })
})

describe('answers survive paging back', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('restores the choice you gave and the time you took', () => {
    // The card is keyed on the question id, so anything the drill does not
    // hold is destroyed on the way out and rebuilt blank on the way back —
    // which made `P` a way to lose your work rather than review it.
    render(<Drill section="LR" />)
    fireEvent.keyDown(window, { key: 'c' })
    act(() => {
      vi.advanceTimersByTime(5_000)
    })
    expect(screen.getByLabelText('Time on this question')).toHaveTextContent('0:05')

    fireEvent.keyDown(window, { key: 'Enter' })
    fireEvent.keyDown(window, { key: 'n' })
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(screen.getByLabelText('Time on this question')).toHaveTextContent('0:00')

    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(radios()[2]).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
    // The restored clock is the time it was answered in, not a fresh 0:00.
    expect(screen.getByLabelText('Time on this question')).toHaveTextContent('0:05')
  })
})

describe('the page announces where a move landed', () => {
  it('moves focus to the new question and reads the position into the live region', () => {
    render(<Page />)
    fireEvent.click(screen.getByRole('button', { name: 'Logical Reasoning' }))
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    // Entering a section must not steal focus out of the nav the reader is
    // still tabbing, so nothing is announced until they actually move.
    expect(screen.getByRole('status')).toHaveTextContent('')

    fireEvent.keyDown(window, { key: 'n' })
    expect(document.activeElement).toBe(card())
    expect(screen.getByRole('status')).toHaveTextContent('Question 2 of 3.')

    fireEvent.keyDown(window, { key: 'p' })
    expect(document.activeElement).toBe(card())
    expect(screen.getByRole('status')).toHaveTextContent('Question 1 of 3.')
  })
})

describe('O reaches the essay editor', () => {
  it('opens the writing prompt and puts the caret in the textarea', () => {
    // O is the only key into the section; opening a prompt but leaving focus
    // six Tab stops from the textarea made it useless on its own.
    render(<Page />)
    fireEvent.click(screen.getByRole('button', { name: 'Argumentative Writing' }))
    expect(screen.getByRole('button', { name: 'Open prompt' })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'o' })
    const editor = screen.getByRole('textbox')
    expect(editor).toHaveAttribute('id', 'writing-draft')
    expect(document.activeElement).toBe(editor)
  })
})
