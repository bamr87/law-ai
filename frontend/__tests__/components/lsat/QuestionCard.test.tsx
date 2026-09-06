import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import QuestionCard from '@/components/lsat/QuestionCard'
import type { LsatQuestion } from '@/lib/api'
import { server } from '@/mocks/server'

const question: LsatQuestion = {
  id: 'lr-001',
  section: 'LR',
  type: 'LR',
  difficulty: 'med',
  stem: 'All swans observed are white. Therefore all swans are white.',
  choices: [
    { label: 'A', text: 'Alpha' },
    { label: 'B', text: 'Bravo' },
    { label: 'C', text: 'Charlie' },
    { label: 'D', text: 'Delta' },
    { label: 'E', text: 'Echo' },
  ],
  concepts: ['flaw-in-reasoning'],
  references: [],
  passage_id: null,
}

beforeEach(() => {
  server.use(
    http.post('http://localhost:8000/api/lsat/grade', () =>
      HttpResponse.json({
        question_id: 'lr-001',
        correct: false,
        correct_choice: 'C',
        explanation: 'Hasty generalisation.',
        section: 'LR',
        concepts: ['flaw-in-reasoning'],
      }),
    ),
  )
})

describe('QuestionCard', () => {
  it('renders the stem, the difficulty badge and one radiogroup of choices', () => {
    render(<QuestionCard question={question} onResolved={() => {}} />)
    expect(screen.getByText(/All swans observed/)).toBeInTheDocument()
    expect(screen.getByText('Medium')).toBeInTheDocument()
    expect(
      screen.getByRole('radiogroup', { name: /answer choices/i }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(5)
    // Submit is gated on a selection.
    expect(screen.getByRole('button', { name: /^Submit$/ })).toBeDisabled()
  })

  it('grades the selected choice and reports the attempt upward', async () => {
    const onResolved = vi.fn()
    render(<QuestionCard question={question} onResolved={onResolved} />)
    fireEvent.click(screen.getByRole('radio', { name: /A.*Alpha/ }))
    expect(screen.getByRole('radio', { name: /A.*Alpha/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    fireEvent.click(screen.getByRole('button', { name: /^Submit$/ }))

    expect(
      await screen.findByText(/Incorrect — answer was C/, {}, { timeout: 5000 }),
    ).toBeInTheDocument()
    expect(onResolved).toHaveBeenCalledTimes(1)
    expect(onResolved.mock.calls[0][0]).toMatchObject({ correct_choice: 'C' })
    // Graded choices stay in the focus order (aria-disabled, never disabled).
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toHaveAttribute('aria-disabled', 'true')
      expect(radio).not.toBeDisabled()
    }
  })

  // BL-20260702-13: the static drill's contract, ported. Focus and selection
  // never diverge, so Enter can only ever grade the answer on screen.
  describe('keyboard contract', () => {
    function radios() {
      return screen.getAllByRole('radio')
    }

    it('moves focus with a letter key, not just the selection', () => {
      render(<QuestionCard question={question} onResolved={() => {}} />)
      const [alpha, bravo] = radios()
      alpha.focus()

      fireEvent.keyDown(alpha, { key: 'b' })
      expect(bravo).toHaveAttribute('aria-checked', 'true')
      expect(document.activeElement).toBe(bravo)
    })

    it('selects with Enter on a choice that is not the selected one', async () => {
      const onResolved = vi.fn()
      render(<QuestionCard question={question} onResolved={onResolved} />)
      const [alpha, , charlie] = radios()

      fireEvent.click(alpha)
      expect(alpha).toHaveAttribute('aria-checked', 'true')

      // Focus a different choice and press Enter: the static drill selects it
      // rather than grading the one that happens to be checked.
      charlie.focus()
      fireEvent.keyDown(charlie, { key: 'Enter' })
      expect(charlie).toHaveAttribute('aria-checked', 'true')
      expect(alpha).toHaveAttribute('aria-checked', 'false')
      expect(onResolved).not.toHaveBeenCalled()
    })

    it('submits with Enter on the choice that is selected', async () => {
      const onResolved = vi.fn()
      render(<QuestionCard question={question} onResolved={onResolved} />)
      const [, bravo] = radios()

      fireEvent.click(bravo)
      bravo.focus()
      fireEvent.keyDown(bravo, { key: 'Enter' })

      expect(
        await screen.findByText(/Incorrect — answer was C/, {}, { timeout: 5000 }),
      ).toBeInTheDocument()
      expect(onResolved).toHaveBeenCalledTimes(1)
    })

    // BL-20260901-06: the letters were bound to this card's DOM subtree, so
    // nothing at all happened until you had tabbed or clicked into it — while
    // the published static site drilled from the keyboard on load.
    it('answers a letter with no focus inside the card at all', () => {
      render(<QuestionCard question={question} onResolved={() => {}} />)
      expect(document.activeElement).toBe(document.body)
      fireEvent.keyDown(document.body, { key: 'd' })
      const [, , , delta] = radios()
      expect(delta).toHaveAttribute('aria-checked', 'true')
      // …and focus follows the letter, so Enter grades what is on screen.
      expect(document.activeElement).toBe(delta)
    })

    it('leaves a letter typed into the tutor follow-up box alone', () => {
      render(
        <>
          <input aria-label="follow-up" />
          <QuestionCard question={question} onResolved={() => {}} />
        </>,
      )
      fireEvent.keyDown(screen.getByLabelText('follow-up'), { key: 'a' })
      expect(radios()[0]).toHaveAttribute('aria-checked', 'false')
    })

    it('still submits from Enter typed outside the choice list', async () => {
      render(<QuestionCard question={question} onResolved={() => {}} />)
      const [alpha] = radios()
      fireEvent.click(alpha)

      // Enter on the card itself, not on a radio — the drill has always meant
      // "grade what I picked" there, and that has not changed.
      fireEvent.keyDown(screen.getByText(/All swans observed/), {
        key: 'Enter',
      })
      expect(
        await screen.findByText(/Incorrect — answer was C/, {}, { timeout: 5000 }),
      ).toBeInTheDocument()
    })
  })
})
