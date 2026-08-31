/** Tests for the question-set review panel (spec 041 FR-15). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ValidationReport from '@/components/lsat/ValidationReport'

describe('ValidationReport', () => {
  it('runs the review and renders counts, issues, distribution, and cross-checks', async () => {
    render(<ValidationReport />)
    fireEvent.click(screen.getByRole('button', { name: /run review/i }))

    await waitFor(() =>
      expect(screen.getByText(/126 questions/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/40 solve guides/)).toBeInTheDocument()
    expect(screen.getByText(/1 integrity issue/)).toBeInTheDocument()
    expect(screen.getByText('lr-099')).toBeInTheDocument()
    expect(screen.getByText(/ghost-concept/)).toBeInTheDocument()

    // Answer-key distribution rendered as an accessible table of counts.
    const table = screen.getByRole('table')
    expect(table).toBeInTheDocument()
    expect(screen.getByRole('rowheader', { name: 'LR' })).toBeInTheDocument()
    expect(
      screen.getByText(/counts, not correctness/i),
    ).toBeInTheDocument()

    // Cross-check roll-up lists the flagged disagreement by question.
    expect(screen.getByText(/2 checked/)).toBeInTheDocument()
    expect(screen.getByText(/1 agree/)).toBeInTheDocument()
    expect(screen.getByText('lr-007')).toBeInTheDocument()
    expect(screen.getByText(/re-verify the answer key/i)).toBeInTheDocument()
  })
})
