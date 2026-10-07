/**
 * What the drill publishes as the section clock's pace denominator.
 *
 * `SectionTimer.test.tsx` exercises the readout by calling
 * `setRemainingQuestions` itself, which is exactly why it could not catch this:
 * the defect was in the number `Drill` hands the store, not in the arithmetic
 * that renders it. The drill published `bank - graded`, so a 99-question
 * Logical Reasoning bank quoted "0:21 left / q" in the visual position of an
 * official per-question budget — against a section whose own copy, one element
 * away in the same header, says ~1:25.
 *
 * `frontend/components/lsat/LrPanel.tsx` has been right since BL-20260905-32;
 * only half of that fix crossed. `make ui-sync` mirrors `lib/` verbatim, so
 * `LSAT_SECTION_QUESTIONS` arrived here automatically while its call site —
 * which lives in `components/`, and is an independent implementation on each
 * side — did not. This suite renders `Drill` end to end so the next `lib/`-plus-
 * call-site change cannot land half-shipped in silence.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import Drill from '@/components/Drill'
import { LSAT_SECTION_QUESTIONS } from '@/lib/lsatTimer'
import { __resetTimerStore } from '@/lib/lsat/timerStore'
import { SECTION_LR } from './fixtures'
import type { Question } from '@/lib/types'

/** A bank of `n` interchangeable LR questions — only its SIZE is under test. */
function bank(n: number): Question[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `lr-pace-${String(i).padStart(3, '0')}`,
    section: 'LR' as const,
    type: 'Assumption',
    difficulty: 'medium',
    stem: `Pace fixture stem ${i}.`,
    choices: ['A', 'B', 'C', 'D', 'E'].map((label) => ({
      label,
      text: `Choice ${label} of ${i}`,
    })),
    correct: 'C',
    explanation: `Explanation ${i}.`,
  }))
}

// The bank the mocked `@/lib/data` serves. Reassigned per test, and read
// lazily by the mock factory so each test picks its own size.
let BANK: Question[] = []

vi.mock('@/lib/data', () => ({
  questionsFor: () => BANK,
  sectionMeta: () => SECTION_LR,
  passageById: () => undefined,
  guideFor: () => undefined,
  conceptById: () => undefined,
}))

/** The `N:NN left / q` readout, or null when the clock declines to quote one. */
function pace(): string | null {
  return screen.queryByLabelText(/time remaining per question/i)?.textContent ?? null
}

/**
 * Answer and grade the current question, then advance.
 *
 * Clicks rather than keystrokes, deliberately. `Drill.test.tsx` drives the
 * keyboard by dispatching on `window`, which works for the first question and
 * then stops: both components bind `Enter` on the window, `useShortcuts`
 * claims an event by calling `preventDefault()` before dispatching, and
 * remounting `QuestionCard` (it is keyed on the question id) re-registers its
 * listener *after* the drill's. A real browser never reaches that race —
 * focus is on the choice, so React's own `onKeyDown` grades and claims the
 * event first — but a synthetic `window` dispatch skips the element handler
 * entirely. Clicks exercise the same state without depending on listener
 * order, which is not what this suite is about.
 */
function gradeAndAdvance(): void {
  const choices = screen.getByRole('radiogroup', { name: 'Answer choices' })
  fireEvent.click(within(choices).getAllByRole('radio')[0])
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
  const nav = screen.getByRole('navigation', { name: 'Question navigation' })
  fireEvent.click(within(nav).getByRole('button', { name: /Next/ }))
}

describe('Drill pace denominator', () => {
  beforeEach(() => {
    __resetTimerStore()
  })
  afterEach(() => {
    __resetTimerStore()
  })

  it('paces one real section, not the whole bank', () => {
    // THE DEFECT. 35:00 ÷ 99 ≈ 0:21 — arithmetically true of the bank, and a
    // speed that does not exist on the exam. 35:00 ÷ 25 = 1:24, which is the
    // "~1:25 per question" the section metadata states.
    BANK = bank(99)
    render(<Drill section="LR" />)

    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(pace()).toBe('1:24 left / q')
    expect(pace()).not.toContain('0:21')
  })

  it('caps at the bank when the bank cannot fill a section', () => {
    // `Math.min` and not a bare constant: a three-question bank has three
    // questions left, and quoting a 25-item pace for it would be the same
    // class of lie in the other direction. 35:00 ÷ 3 = 11:40.
    BANK = bank(3)
    render(<Drill section="LR" />)

    expect(pace()).toBe('11:40 left / q')
  })

  it('blanks the readout past a full section rather than going negative', () => {
    // A bank one question larger than a section, graded past the section
    // boundary. Unclamped this publishes `30 - 26 = 4` and cheerfully quotes
    // 8:45 for a section that is over; clamped it publishes 0, and
    // `secondsPerQuestion` returns null, which hides the readout.
    const graded = LSAT_SECTION_QUESTIONS + 1
    BANK = bank(LSAT_SECTION_QUESTIONS + 5)
    render(<Drill section="LR" />)
    expect(pace()).toBe('1:24 left / q')

    for (let i = 0; i < graded; i += 1) gradeAndAdvance()

    expect(pace()).toBeNull()
  })
})
