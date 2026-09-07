/**
 * Per-attempt answer shuffling in the offline drill (BL-20260606-01).
 *
 * The platform proves this over HTTP (a signed remap token); the static site
 * has no server, so the permutation is drawn in the browser and the same three
 * things have to hold: the choices move, the key moves with them, and what is
 * written down afterwards is still in the bank's own labels.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import QuestionCard from '@/components/QuestionCard'
import type { Question } from '@/lib/types'
import {
  displayMapping,
  identityOrder,
  orderFor,
  permuteQuestion,
  presetOrder,
  remapLabels,
  resetOrders,
  toCanonical,
  toDisplay,
} from '@/lib/shuffle'

const QUESTION: Question = {
  id: 'lr-shuffle-01',
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
  explanation: 'C is correct because the argument needs it.',
}

function radios(): HTMLElement[] {
  return within(
    screen.getByRole('radiogroup', { name: 'Answer choices' }),
  ).getAllByRole('radio')
}

describe('shuffle helpers', () => {
  beforeEach(() => resetOrders())

  it('relabels the board top to bottom and moves the key with it', () => {
    presetOrder(QUESTION.id, [2, 0, 4, 1, 3])
    const shown = permuteQuestion(QUESTION)
    expect(shown.choices.map((c) => c.label)).toEqual(['A', 'B', 'C', 'D', 'E'])
    expect(shown.choices.map((c) => c.text)).toEqual([
      'Choice C',
      'Choice A',
      'Choice E',
      'Choice B',
      'Choice D',
    ])
    expect(shown.correct).toBe('A')
    expect(shown.explanation).toBe('A is correct because the argument needs it.')
  })

  it('keeps one order per question for the session', () => {
    const first = orderFor('lr-x', 5)
    expect(orderFor('lr-x', 5)).toEqual(first)
    resetOrders()
    // A new session may well draw the same board; what matters is that the
    // stored one was dropped, which the map size cannot show from outside.
    expect(orderFor('lr-x', 5)).toHaveLength(5)
  })

  it('maps labels both ways', () => {
    const order = [3, 1, 4, 0, 2]
    for (const label of ['A', 'B', 'C', 'D', 'E']) {
      expect(toCanonical(toDisplay(label, order), order)).toBe(label)
    }
    expect(displayMapping(identityOrder(5))).toEqual({
      A: 'A',
      B: 'B',
      C: 'C',
      D: 'D',
      E: 'E',
    })
  })

  it('rewrites label references without touching prose', () => {
    const mapping = { A: 'B', B: 'A' }
    expect(remapLabels('A is wrong, B is right.', mapping)).toBe(
      'B is wrong, A is right.',
    )
    expect(remapLabels('A recent study found the opposite.', mapping)).toBe(
      'A recent study found the opposite.',
    )
    expect(remapLabels('(B) is the exception.', mapping)).toBe(
      '(A) is the exception.',
    )
  })
})

describe('QuestionCard under a shuffle', () => {
  beforeEach(() => resetOrders())

  it('grades the choice on screen and records the stored label', () => {
    presetOrder(QUESTION.id, [2, 0, 4, 1, 3])
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
    // Stored C is displayed first, so picking the first choice is correct.
    fireEvent.click(radios()[0])
    fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
    expect(onAnnounce).toHaveBeenLastCalledWith('Correct.')
    expect(onAnswered).toHaveBeenCalledWith('C', expect.any(Number))
    expect(screen.getByText(/^Correct$/)).toBeInTheDocument()
  })

  it('names the displayed key when the answer is wrong', () => {
    presetOrder(QUESTION.id, [2, 0, 4, 1, 3])
    const onAnnounce = vi.fn()
    render(
      <QuestionCard
        question={QUESTION}
        index={0}
        total={1}
        onAnnounce={onAnnounce}
      />,
    )
    fireEvent.click(radios()[1])
    fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
    expect(onAnnounce).toHaveBeenLastCalledWith(
      'Incorrect. The correct answer is A.',
    )
    expect(screen.getByText(/incorrect — the answer is a/i)).toBeInTheDocument()
    // The explanation speaks in the labels on screen, not the stored ones.
    expect(
      screen.getByText('A is correct because the argument needs it.'),
    ).toBeInTheDocument()
  })

  it('restores a saved answer into the board it is showing', () => {
    presetOrder(QUESTION.id, [2, 0, 4, 1, 3])
    render(
      <QuestionCard question={QUESTION} index={0} total={1} savedChoice="A" />,
    )
    // Stored A sits second under this order, so that is the checked one.
    const checked = radios().filter(
      (r) => r.getAttribute('aria-checked') === 'true',
    )
    expect(checked).toHaveLength(1)
    expect(checked[0]).toHaveTextContent('Choice A')
  })
})
