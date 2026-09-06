/**
 * The answer-choice radiogroup keyboard contract (BL-20260831-18).
 *
 * The platform pins the same pattern in frontend/__tests__/shell/; this is
 * the static site's half, dispatching real key events instead of asserting
 * source strings from tests/test_lsat_site.py.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import QuestionCard from '@/components/QuestionCard'
import type { Question } from '@/lib/types'

const QUESTION: Question = {
  id: 'lr-test-01',
  section: 'LR',
  type: 'Assumption',
  difficulty: 'medium',
  stem: 'Which one of the following is an assumption the argument requires?',
  choices: [
    { label: 'A', text: 'Choice A' },
    { label: 'B', text: 'Choice B' },
    { label: 'C', text: 'Choice C' },
    { label: 'D', text: 'Choice D' },
    { label: 'E', text: 'Choice E' },
  ],
  correct: 'C',
  explanation: 'Because C is what the argument needs.',
}

function radios(): HTMLElement[] {
  return within(
    screen.getByRole('radiogroup', { name: 'Answer choices' }),
  ).getAllByRole('radio')
}

function checked(): string[] {
  return radios()
    .filter((r) => r.getAttribute('aria-checked') === 'true')
    .map((r) => r.textContent?.trim().charAt(0) ?? '')
}

describe('QuestionCard radiogroup', () => {
  it('is a single tab stop before anything is selected', () => {
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    const stops = radios().filter((r) => r.tabIndex === 0)
    expect(stops).toHaveLength(1)
    expect(stops[0]).toBe(radios()[0])
  })

  it('moves focus and selection with the arrow keys, wrapping at both ends', () => {
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    const [a, b] = radios()
    a.focus()

    fireEvent.keyDown(a, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(radios()[1])
    expect(checked()).toEqual(['B'])
    // Selection follows focus: the tab stop moves with it.
    expect(radios()[1].tabIndex).toBe(0)
    expect(radios()[0].tabIndex).toBe(-1)

    fireEvent.keyDown(b, { key: 'ArrowRight' })
    expect(checked()).toEqual(['C'])

    fireEvent.keyDown(radios()[2], { key: 'ArrowUp' })
    fireEvent.keyDown(radios()[1], { key: 'ArrowLeft' })
    fireEvent.keyDown(radios()[0], { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(radios()[4])
    expect(checked()).toEqual(['E'])

    fireEvent.keyDown(radios()[4], { key: 'ArrowDown' })
    expect(document.activeElement).toBe(radios()[0])
    expect(checked()).toEqual(['A'])
  })

  it('jumps to the first and last choice with Home and End', () => {
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    const [a] = radios()
    a.focus()
    fireEvent.keyDown(a, { key: 'End' })
    expect(document.activeElement).toBe(radios()[4])
    expect(checked()).toEqual(['E'])
    fireEvent.keyDown(radios()[4], { key: 'Home' })
    expect(document.activeElement).toBe(radios()[0])
    expect(checked()).toEqual(['A'])
  })

  it('never steals a modified arrow chord (shared roving-focus contract)', () => {
    // Ctrl/Cmd/Alt+Arrow is word-jump, desktop switching, or history
    // navigation depending on the platform; nextRovingIndex leaves it alone
    // and so, now, does the static card (BL-20260831-08).
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    const [a] = radios()
    a.focus()
    fireEvent.keyDown(a, { key: 'ArrowDown', metaKey: true })
    fireEvent.keyDown(a, { key: 'ArrowDown', ctrlKey: true })
    fireEvent.keyDown(a, { key: 'ArrowDown', altKey: true })
    expect(document.activeElement).toBe(radios()[0])
    expect(checked()).toEqual([])
  })

  it('selects with Space and submits with Enter on the selected choice', () => {
    const onAnswered = vi.fn()
    const onAnnounce = vi.fn()
    render(
      <QuestionCard
        question={QUESTION}
        index={0}
        total={1}
        onAnswered={onAnswered}
        onAnnounce={onAnnounce}
      />,
    )
    const c = radios()[2]
    c.focus()
    fireEvent.keyDown(c, { key: ' ' })
    expect(checked()).toEqual(['C'])
    expect(screen.queryByRole('region', { name: 'Explanation' })).toBeNull()

    // Enter on an unselected choice selects it rather than submitting.
    fireEvent.keyDown(radios()[1], { key: 'Enter' })
    expect(checked()).toEqual(['B'])
    expect(screen.queryByRole('region', { name: 'Explanation' })).toBeNull()

    fireEvent.keyDown(radios()[2], { key: 'Enter' })
    expect(checked()).toEqual(['C'])
    fireEvent.keyDown(radios()[2], { key: 'Enter' })
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
    expect(onAnswered).toHaveBeenCalledWith('C', expect.any(Number))
    expect(onAnnounce).toHaveBeenCalledWith('Correct.')
  })

  it('picks a choice from a bare letter key anywhere on the page', () => {
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    fireEvent.keyDown(window, { key: 'd' })
    expect(checked()).toEqual(['D'])
    expect(document.activeElement).toBe(radios()[3])
    // Uppercase (Shift held) is the same letter.
    fireEvent.keyDown(window, { key: 'B', shiftKey: true })
    expect(checked()).toEqual(['B'])
  })

  it('keeps graded choices focusable and inert', () => {
    render(<QuestionCard question={QUESTION} index={0} total={1} />)
    const b = radios()[1]
    b.focus()
    fireEvent.keyDown(b, { key: ' ' })
    fireEvent.keyDown(b, { key: 'Enter' })
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()

    // Focus did not fall to <body>: the graded choice is aria-disabled, not
    // disabled, so it stays in the focus order.
    expect(document.activeElement).toBe(radios()[1])
    for (const r of radios()) {
      expect(r).toHaveAttribute('aria-disabled', 'true')
      expect(r).not.toBeDisabled()
    }
    radios()[3].focus()
    expect(document.activeElement).toBe(radios()[3])

    // ...but nothing moves the selection any more.
    fireEvent.keyDown(radios()[1], { key: 'ArrowDown' })
    fireEvent.keyDown(window, { key: 'a' })
    fireEvent.click(radios()[0])
    expect(checked()).toEqual(['B'])
    expect(screen.getByText(/incorrect — the answer is c/i)).toBeInTheDocument()
  })

  it('mounts in the graded state when handed a saved answer', () => {
    render(
      <QuestionCard
        question={QUESTION}
        index={0}
        total={1}
        savedChoice="C"
        savedSeconds={42}
      />,
    )
    expect(checked()).toEqual(['C'])
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
    expect(screen.getByLabelText('Time on this question')).toHaveTextContent('0:42')
  })
})
