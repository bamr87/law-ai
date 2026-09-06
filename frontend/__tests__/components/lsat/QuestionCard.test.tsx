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
})
