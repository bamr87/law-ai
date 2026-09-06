/**
 * The static section clock, now a view over the shared timer store
 * (BL-20260830-04). The store itself is the platform's file, mirrored here by
 * `make ui-sync` and byte-gated by ux_audit R12 — so what is worth asserting
 * on this side is that the static markup really is driven by it: the clock the
 * drill shows, the Start/Pause/Reset controls, and the pace readouts.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SectionTimer from '@/components/SectionTimer'
import {
  __resetTimerStore,
  pauseTimer,
  recordAnswer,
  resetSection,
  setRemainingQuestions,
  startTimer,
} from '@/lib/lsat/timerStore'

describe('SectionTimer', () => {
  beforeEach(() => {
    __resetTimerStore()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    __resetTimerStore()
  })

  it('shows a 35-minute clock and per-question pace before starting', () => {
    setRemainingQuestions(25)
    render(<SectionTimer />)
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('1:24 left / q')
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('counts down while running and pauses without losing remaining time', () => {
    render(<SectionTimer />)
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
    render(<SectionTimer />)
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('reads the same clock a second mount is already showing', () => {
    // The point of the store: two views, one section. Before it, a remount
    // (moving the widget, or a refresh) restarted the clock.
    render(<SectionTimer />)
    act(() => {
      startTimer()
      vi.advanceTimersByTime(2000)
    })
    render(<SectionTimer />)
    for (const clock of screen.getAllByRole('timer')) {
      expect(clock).toHaveTextContent('34:58')
    }
  })

  it('reports the average pace once questions have been answered', () => {
    setRemainingQuestions(25)
    render(<SectionTimer />)
    expect(
      screen.queryByLabelText(/average time per question/i),
    ).not.toBeInTheDocument()

    act(() => {
      recordAnswer(90)
    })
    expect(
      screen.getByLabelText(/average time per question/i),
    ).toHaveTextContent('avg 1:30 / q')

    act(() => {
      recordAnswer(78)
    })
    expect(
      screen.getByLabelText(/average time per question/i),
    ).toHaveTextContent('avg 1:24 / q')
  })

  it('clears the pace counters when the drill switches section', () => {
    setRemainingQuestions(25)
    render(<SectionTimer />)
    act(() => {
      recordAnswer(90)
    })
    expect(
      screen.getByLabelText(/average time per question/i),
    ).toBeInTheDocument()

    act(() => {
      resetSection()
    })
    expect(
      screen.queryByLabelText(/average time per question/i),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
  })

  it('hides the pace readout until the drill says how many are left', () => {
    render(<SectionTimer />)
    expect(
      screen.queryByLabelText(/time remaining per question/i),
    ).not.toBeInTheDocument()

    act(() => {
      setRemainingQuestions(25)
    })
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('1:24 left / q')

    // Down to ten left, the same 35 minutes buys 3:30 apiece.
    act(() => {
      setRemainingQuestions(10)
    })
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('3:30 left / q')

    act(() => {
      setRemainingQuestions(null)
    })
    expect(
      screen.queryByLabelText(/time remaining per question/i),
    ).not.toBeInTheDocument()
  })

  it('offers 5 / 10 / 35 minute drill presets', () => {
    render(<SectionTimer />)
    const presets = screen.getByRole('radiogroup', { name: 'Drill length' })
    expect(
      Array.from(presets.querySelectorAll('button')).map((b) => b.textContent),
    ).toEqual(['5 min', '10 min', '35 min'])

    fireEvent.click(screen.getByRole('radio', { name: '10 min' }))
    expect(screen.getByRole('timer')).toHaveTextContent('10:00')
    expect(screen.getByRole('radio', { name: '10 min' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('paces a short drill against the short clock', () => {
    render(<SectionTimer />)
    fireEvent.click(screen.getByRole('radio', { name: '5 min' }))
    act(() => {
      setRemainingQuestions(5)
    })
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('1:00 left / q')
  })

  it('locks the presets once a section is under way', () => {
    render(<SectionTimer />)
    act(() => {
      startTimer()
      vi.advanceTimersByTime(2000)
      pauseTimer()
    })
    for (const preset of screen.getAllByRole('radio')) {
      expect(preset).toBeDisabled()
    }
  })

  it('keeps a chosen preset across a section switch', () => {
    render(<SectionTimer />)
    fireEvent.click(screen.getByRole('radio', { name: '10 min' }))
    act(() => {
      resetSection()
    })
    expect(screen.getByRole('timer')).toHaveTextContent('10:00')
  })
})
