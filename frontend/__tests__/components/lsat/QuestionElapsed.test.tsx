import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { QuestionElapsed } from '@/components/lsat/QuestionElapsed'

/**
 * These cases moved wholesale from `__tests__/components/LsatTimer.test.tsx`
 * when the per-question stopwatch was folded into `components/lsat/`
 * (BL-20260831-15). The `describe('LsatTimer')` block that sat beside them
 * covered a section clock the app stopped rendering in spec 043; the live
 * clock is `SectionTimerWidget`, covered by `__tests__/shell/lsatTimerDock`.
 */
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

  it('banks time already spent on a revisited question via startAt', () => {
    render(<QuestionElapsed frozen={false} startAt={65} />)
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '1:05',
    )
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '1:07',
    )
  })

  it('reports the banked total to onTick when it freezes', () => {
    const onTick = vi.fn()
    const { rerender } = render(
      <QuestionElapsed frozen={false} startAt={10} onTick={onTick} />,
    )
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    rerender(<QuestionElapsed frozen={true} startAt={10} onTick={onTick} />)
    expect(onTick).toHaveBeenLastCalledWith(13)
  })
})
