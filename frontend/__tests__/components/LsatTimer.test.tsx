import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LsatTimer, { QuestionElapsed } from '@/components/LsatTimer'

describe('LsatTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a 35-minute clock and per-question pace before starting', () => {
    render(<LsatTimer remainingQuestions={25} />)
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(screen.getByLabelText(/time remaining per question/i)).toHaveTextContent(
      '1:24 left / q',
    )
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('counts down while running and pauses without losing remaining time', () => {
    render(<LsatTimer />)
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByRole('timer')).toHaveTextContent('34:59')

    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByRole('timer')).toHaveTextContent('34:59')
  })

  it('resets to the full section length', () => {
    render(<LsatTimer durationSeconds={10} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByRole('timer')).toHaveTextContent('0:10')
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('announces time expired without locking the learner out', () => {
    render(<LsatTimer durationSeconds={1} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByRole('timer')).toHaveTextContent('0:00')
    expect(screen.getByRole('status')).toHaveTextContent(/time's up/i)
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
  })

  it('updates the average minutes-per-question rate after answers', () => {
    const { rerender } = render(
      <LsatTimer remainingQuestions={25} answeredCount={0} answeredSeconds={0} />,
    )
    expect(screen.queryByLabelText(/average time per question/i)).not.toBeInTheDocument()

    rerender(
      <LsatTimer remainingQuestions={24} answeredCount={1} answeredSeconds={90} />,
    )
    expect(screen.getByLabelText(/average time per question/i)).toHaveTextContent(
      'avg 1:30 / q',
    )
    expect(screen.getByLabelText(/time remaining per question/i)).toHaveTextContent(
      '1:27 left / q',
    )

    rerender(
      <LsatTimer remainingQuestions={23} answeredCount={2} answeredSeconds={168} />,
    )
    expect(screen.getByLabelText(/average time per question/i)).toHaveTextContent(
      'avg 1:24 / q',
    )
  })
})

describe('QuestionElapsed', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('counts up until frozen and resets on a new question', () => {
    const { rerender } = render(<QuestionElapsed key="lr-001" frozen={false} />)
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:02',
    )

    rerender(<QuestionElapsed key="lr-001" frozen={true} />)
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:02',
    )

    rerender(<QuestionElapsed key="lr-002" frozen={false} />)
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )
  })

  it('resumes from elapsed time when unfrozen without remounting', () => {
    const { rerender } = render(<QuestionElapsed frozen={false} />)
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    rerender(<QuestionElapsed frozen={true} />)
    rerender(<QuestionElapsed frozen={false} />)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:03',
    )
  })
})
