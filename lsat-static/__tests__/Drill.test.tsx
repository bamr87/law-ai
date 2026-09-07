/**
 * Running a whole drill from the keyboard (BL-20260901-07).
 *
 * The drill is where the two window-level `Enter` listeners meet: QuestionCard
 * submits with it, Drill advances with it, and both bind it on the same window.
 * That only works because `useShortcuts` skips an event another listener has
 * claimed *and* because QuestionCard stops binding `Enter` once the question is
 * graded — a permanently-bound, no-op `Enter` there starved the advance. This
 * suite dispatches the real key events that a browser pass used to have to.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Drill from '@/components/Drill'
import { identityOrder, presetOrder, resetOrders } from '@/lib/shuffle'
import { recordAnswer } from '@/lib/lsat/timerStore'

// A pass-through spy: the section clock is the real store, but a test can see
// how many times the drill billed it (BL-20260905-34).
vi.mock('@/lib/lsat/timerStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/lsat/timerStore')>()
  return { ...actual, recordAnswer: vi.fn(actual.recordAnswer) }
})

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    questionsFor: () => f.QUESTIONS,
    sectionMeta: () => f.SECTION_LR,
    passageById: () => undefined,
    guideFor: () => undefined,
    conceptById: () => undefined,
  }
})

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

function card(): HTMLElement {
  return screen.getByRole('article')
}

describe('Drill keyboard flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // Choices are shuffled per attempt (BL-20260606-01). This suite is about
    // keyboard wiring, not about the shuffle, so it pins the identity order
    // and keeps asserting on the bank's own labels.
    resetOrders()
    for (const id of ['lr-fixture-01', 'lr-fixture-02', 'lr-fixture-03']) {
      presetOrder(id, identityOrder(5))
    }
  })

  it('answers with a letter, grades with Enter, and advances with Enter again', () => {
    // The regression this file exists for: before QuestionCard stopped binding
    // `Enter` at grade time, the second press was swallowed and the drill sat
    // on the graded question forever.
    render(<Drill section="LR" />)
    expect(card()).toHaveAccessibleName('Question 1 of 3')

    fireEvent.keyDown(window, { key: 'c' })
    expect(checked()).toEqual(['C'])

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(screen.getByRole('region', { name: 'Explanation' })).toHaveTextContent(
      'Explanation 1.',
    )
    expect(card()).toHaveAccessibleName('Question 1 of 3')

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(screen.queryByRole('region', { name: 'Explanation' })).toBeNull()
  })

  it('does not advance on Enter until the question has been checked', () => {
    render(<Drill section="LR" />)
    // Nothing selected: neither listener acts, and the drill stays put.
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    // Selected but not yet graded: Enter belongs to QuestionCard.
    fireEvent.keyDown(window, { key: 'a' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
  })

  it('moves with N and P, and clamps at both ends', () => {
    render(<Drill section="LR" />)
    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')

    fireEvent.keyDown(window, { key: 'n' })
    fireEvent.keyDown(window, { key: 'n' })
    expect(card()).toHaveAccessibleName('Question 3 of 3')
    fireEvent.keyDown(window, { key: 'n' })
    expect(card()).toHaveAccessibleName('Question 3 of 3')

    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 2 of 3')
  })

  it('keeps the answer you gave when you page back to a question', () => {
    // The card is keyed on the question id, so anything the drill does not
    // hold is destroyed on the way out — which made `P` a way to lose work.
    render(<Drill section="LR" />)
    fireEvent.keyDown(window, { key: 'c' })
    fireEvent.keyDown(window, { key: 'Enter' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(checked()).toEqual([])

    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(checked()).toEqual(['C'])
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()
  })

  it('bills the section clock once per question, however often you page back', () => {
    // The drill keeps the answer and its elapsed time in its own Map, while
    // the shared store accumulates the section total. Both are written on the
    // *first* answer only — a revisited question that could be graded again
    // would drift the two apart (BL-20260905-34).
    vi.mocked(recordAnswer).mockClear()
    render(<Drill section="LR" />)
    fireEvent.keyDown(window, { key: 'c' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(recordAnswer).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: 'Enter' })
    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')

    // Back on a graded question: pressing a letter and Enter again re-grades
    // nothing — Enter belongs to the drill's advance here — so neither
    // accumulator moves and the answer of record is still the first one.
    fireEvent.keyDown(window, { key: 'a' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(recordAnswer).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: 'p' })
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(checked()).toEqual(['C'])
  })

  it('lands focus on the new question and announces the position', () => {
    // Without this, `N` left focus on <body>: no ring for a sighted keyboard
    // user, no position for a screen reader, and Tab restarting at the top.
    const onAnnounce = vi.fn()
    render(<Drill section="LR" onAnnounce={onAnnounce} />)
    // Mounting the section must NOT steal focus out of the nav.
    expect(onAnnounce).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(document.body)

    fireEvent.keyDown(window, { key: 'n' })
    expect(document.activeElement).toBe(card())
    expect(onAnnounce).toHaveBeenLastCalledWith('Question 2 of 3.')

    fireEvent.keyDown(window, { key: 'p' })
    expect(document.activeElement).toBe(card())
    expect(onAnnounce).toHaveBeenLastCalledWith('Question 1 of 3.')
  })

  it('drives the same moves from the nav buttons', () => {
    render(<Drill section="LR" />)
    const nav = screen.getByRole('navigation', { name: 'Question navigation' })
    expect(within(nav).getByRole('button', { name: /Previous/ })).toBeDisabled()
    fireEvent.click(within(nav).getByRole('button', { name: /Next/ }))
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(within(nav).getByRole('button', { name: /Previous/ })).not.toBeDisabled()
  })

  it('announces the verdict when a question is graded', () => {
    const onAnnounce = vi.fn()
    render(<Drill section="LR" onAnnounce={onAnnounce} />)
    fireEvent.keyDown(window, { key: 'b' })
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(onAnnounce).toHaveBeenLastCalledWith(
      'Incorrect. The correct answer is C.',
    )
  })
})
