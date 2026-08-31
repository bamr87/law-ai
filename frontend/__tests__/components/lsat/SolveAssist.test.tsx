/** Carousel-reveal tests for SolveAssist (spec 041 T-008/T-012, AC-4). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SolveAssist, {
  resetSolveAssistSession,
} from '@/components/lsat/SolveAssist'

describe('SolveAssist (carousel)', () => {
  beforeEach(() => {
    resetSolveAssistSession()
  })

  it('reveals one step per hint click, showing a single slide at a time', async () => {
    render(<SolveAssist questionId="lg-001" graded={false} />)

    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    await waitFor(() =>
      expect(screen.getByText('Write out the elements')).toBeInTheDocument(),
    )
    // Exactly one slide on screen.
    expect(screen.getAllByRole('group')).toHaveLength(1)
    expect(screen.getByText(/step 1 of 3/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() =>
      expect(screen.getByText('Symbolize each rule')).toBeInTheDocument(),
    )
    // The carousel replaces the slide — step 1's content is gone from the DOM.
    expect(screen.queryByText('Write out the elements')).not.toBeInTheDocument()
    expect(screen.getAllByRole('group')).toHaveLength(1)
    expect(screen.getByText(/step 2 of 3/i)).toBeInTheDocument()
  })

  it('navigates back and forward through revealed slides without re-revealing', async () => {
    render(<SolveAssist questionId="lg-001" graded={false} />)
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    await waitFor(() => screen.getByText('Write out the elements'))
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() => screen.getByText('Symbolize each rule'))

    fireEvent.click(screen.getByRole('button', { name: /previous step/i }))
    expect(screen.getByText('Write out the elements')).toBeInTheDocument()
    expect(screen.getByText(/step 1 of 3/i)).toBeInTheDocument()
    // Back at the start, Back is disabled.
    expect(screen.getByRole('button', { name: /previous step/i })).toBeDisabled()

    // Forward within revealed steps navigates (labelled plain Next).
    fireEvent.click(screen.getByRole('button', { name: /^next ›$/i }))
    expect(screen.getByText('Symbolize each rule')).toBeInTheDocument()

    // Dots jump directly to a revealed step.
    fireEvent.click(screen.getByRole('button', { name: /go to step 1/i }))
    expect(screen.getByText('Write out the elements')).toBeInTheDocument()
  })

  it('keeps spoiler steps locked until graded, then unlocks via Show final step', async () => {
    const { rerender } = render(
      <SolveAssist questionId="lg-001" graded={false} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    await waitFor(() => screen.getByText('Write out the elements'))
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))

    // Third slide is the spoiler answer step — a locked stub, no content.
    await waitFor(() =>
      expect(
        screen.getByText(/locked — submit an answer/i),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByText(/D is correct/)).not.toBeInTheDocument()
    // Fully revealed: no further hint affordance, and no unlock while ungraded.
    expect(
      screen.queryByRole('button', { name: /next hint/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /show final step/i }),
    ).not.toBeInTheDocument()

    rerender(<SolveAssist questionId="lg-001" graded={true} />)
    fireEvent.click(screen.getByRole('button', { name: /show final step/i }))
    await waitFor(() =>
      expect(screen.getByText(/D is correct/)).toBeInTheDocument(),
    )
    expect(
      screen.queryByText(/locked — submit an answer/i),
    ).not.toBeInTheDocument()
  })

  it('reports hints used, not counting locked stubs', async () => {
    const onHintsUsedChange = vi.fn()
    render(
      <SolveAssist
        questionId="lg-001"
        graded={false}
        onHintsUsedChange={onHintsUsedChange}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    await waitFor(() => expect(onHintsUsedChange).toHaveBeenLastCalledWith(1))
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() => expect(onHintsUsedChange).toHaveBeenLastCalledWith(2))
    // The third (locked) slide is not help.
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() =>
      expect(screen.getByText(/locked — submit an answer/i)).toBeInTheDocument(),
    )
    expect(onHintsUsedChange).toHaveBeenLastCalledWith(2)
  })

  it('offers the AI tutor when the question has no guide', async () => {
    const onAskTutor = vi.fn()
    render(
      <SolveAssist questionId="lr-042" graded={false} onAskTutor={onAskTutor} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    const cta = await screen.findByRole('button', {
      name: /ask the ai tutor for a walkthrough/i,
    })
    fireEvent.click(cta)
    expect(onAskTutor).toHaveBeenCalledTimes(1)
  })

  it('renders diagram representations inside the active slide', async () => {
    render(<SolveAssist questionId="lg-001" graded={false} />)
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    const board = await screen.findByRole('img')
    expect(board.getAttribute('aria-label')).toContain('Slot 4: J')
  })
})
