import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SectionTimerWidget from '@/components/lsat/SectionTimerWidget'
import { resolveDock } from '@/lib/shell/docks'
import { deleteSettingValue } from '@/lib/scope/store'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { lsatTimerDock, type Dock } from '@/lib/settings/catalog'
import {
  __resetTimerStore,
  getTimerSnapshot,
  isSectionInProgress,
  pauseTimer,
  recordAnswer,
  resetTimer,
  startTimer,
} from '@/lib/lsat/timerStore'

const ALL: Dock[] = ['sidebar', 'inspector']

beforeEach(() => {
  __resetTimerStore()
  window.localStorage.clear()
  deleteSettingValue(INSTANCE_SCOPE.id, lsatTimerDock.key)
})
afterEach(() => {
  __resetTimerStore()
  vi.useRealTimers()
})

describe('resolveDock', () => {
  it('honours the preference when that zone is on screen', () => {
    expect(
      resolveDock('inspector', { onOwnRoute: true, openDocks: ALL }),
    ).toBe('inspector')
  })

  it('falls back rather than hiding a clock when the panel is collapsed', () => {
    // Sidebar closed: the timer must surface somewhere, not vanish.
    expect(
      resolveDock('sidebar', { onOwnRoute: false, openDocks: ['inspector'] }),
    ).toBe('inspector')
  })

  it('uses the page itself when no panel is open, on its own route', () => {
    expect(resolveDock('sidebar', { onOwnRoute: true, openDocks: [] })).toBe(
      'inline',
    )
  })

  it('reports nowhere to put it when off-route with every panel closed', () => {
    expect(resolveDock('sidebar', { onOwnRoute: false, openDocks: [] })).toBeNull()
  })

  it('never picks the inline zone off the widget’s own route', () => {
    expect(
      resolveDock('inline', { onOwnRoute: false, openDocks: ['sidebar'] }),
    ).toBe('sidebar')
  })
})

describe('timer store', () => {
  it('counts down from a wall-clock deadline, not accumulated ticks', () => {
    vi.useFakeTimers()
    const start = Date.now()
    startTimer()
    expect(getTimerSnapshot().running).toBe(true)
    vi.setSystemTime(start + 65_000)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    // 35:00 - 1:05 = 33:55. Tick count is irrelevant; elapsed wall time is not.
    expect(getTimerSnapshot().remainingSeconds).toBe(35 * 60 - 65)
  })

  it('holds the remaining time across a pause', () => {
    vi.useFakeTimers()
    const start = Date.now()
    startTimer()
    vi.setSystemTime(start + 10_000)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    pauseTimer()
    const held = getTimerSnapshot().remainingSeconds
    vi.setSystemTime(start + 60_000)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(getTimerSnapshot().remainingSeconds).toBe(held)
    expect(getTimerSnapshot().running).toBe(false)
  })

  it('knows whether a section is in progress', () => {
    expect(isSectionInProgress(getTimerSnapshot())).toBe(false)
    startTimer()
    expect(isSectionInProgress(getTimerSnapshot())).toBe(true)
    resetTimer()
    expect(isSectionInProgress(getTimerSnapshot())).toBe(false)
  })

  it('persists a running section so a refresh does not cost the clock', () => {
    vi.useFakeTimers()
    const start = Date.now()
    startTimer()
    vi.setSystemTime(start + 20_000)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    const blob = window.sessionStorage.getItem('law-ai.lsat.timer.v1')
    expect(blob).toBeTruthy()
    const saved = JSON.parse(blob as string)
    // The deadline is stored, not the remaining seconds: time spent reloading
    // still counts against a running section.
    expect(saved.running).toBe(true)
    expect(typeof saved.deadline).toBe('number')
    expect(saved.deadline).toBeGreaterThan(start)
  })

  it('accumulates pace across answers', () => {
    recordAnswer(40)
    recordAnswer(20)
    expect(getTimerSnapshot().answered).toBe(2)
    expect(getTimerSnapshot().answeredSeconds).toBe(60)
  })
})

function renderDocks(onOwnRoute = true) {
  return render(
    <>
      <div data-testid="zone-sidebar">
        <SectionTimerWidget
          dock="sidebar"
          onOwnRoute={onOwnRoute}
          openDocks={ALL}
        />
      </div>
      <div data-testid="zone-inspector">
        <SectionTimerWidget
          dock="inspector"
          onOwnRoute={onOwnRoute}
          openDocks={ALL}
        />
      </div>
      <div data-testid="zone-inline">
        <SectionTimerWidget
          dock="inline"
          onOwnRoute={onOwnRoute}
          openDocks={ALL}
        />
      </div>
    </>,
  )
}

describe('SectionTimerWidget docking', () => {
  it('docks in the sidebar by default and nowhere else', () => {
    renderDocks()
    const timers = screen.getAllByTestId('lsat-timer')
    expect(timers).toHaveLength(1)
    expect(timers[0]).toHaveAttribute('data-dock', 'sidebar')
  })

  it('moves to the dock chosen from its own menu', () => {
    renderDocks()
    fireEvent.click(screen.getByRole('button', { name: /move the section timer/i }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /In page/ }))

    const timers = screen.getAllByTestId('lsat-timer')
    expect(timers).toHaveLength(1)
    expect(timers[0]).toHaveAttribute('data-dock', 'inline')
  })

  it('keeps a running clock across a move — the whole point of the store', () => {
    vi.useFakeTimers()
    const start = Date.now()
    renderDocks()
    act(() => {
      startTimer()
    })
    vi.setSystemTime(start + 30_000)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    const before = screen.getByRole('timer').textContent

    fireEvent.click(screen.getByRole('button', { name: /move the section timer/i }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /Inspector/ }))

    expect(screen.getByTestId('lsat-timer')).toHaveAttribute(
      'data-dock',
      'inspector',
    )
    // Same clock, not a fresh 35:00.
    expect(screen.getByRole('timer').textContent).toBe(before)
    expect(before).not.toBe('35:00')
    expect(getTimerSnapshot().running).toBe(true)
  })

  it('stays hidden off the LSAT routes until a section is in progress', () => {
    const { rerender } = renderDocks(false)
    expect(screen.queryByTestId('lsat-timer')).not.toBeInTheDocument()

    act(() => {
      startTimer()
    })
    rerender(
      <div data-testid="zone-sidebar">
        <SectionTimerWidget dock="sidebar" onOwnRoute={false} openDocks={ALL} />
      </div>,
    )
    expect(screen.getByTestId('lsat-timer')).toBeInTheDocument()
  })

  it('marks the current dock in the move menu', () => {
    renderDocks()
    fireEvent.click(screen.getByRole('button', { name: /move the section timer/i }))
    expect(screen.getByRole('menuitemradio', { name: /Sidebar/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(
      screen.getByRole('menuitemradio', { name: /Inspector/ }),
    ).toHaveAttribute('aria-checked', 'false')
  })
})
