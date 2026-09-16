import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SectionTimerWidget from '@/components/lsat/SectionTimerWidget'
import { resolveDock } from '@/lib/shell/docks'
import {
  deleteSettingValue,
  listSettingValues,
  upsertSettingValue,
} from '@/lib/scope/store'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import {
  lsatTimerDock,
  lsatTimerDuration,
  lsatTimerVisible,
  type Dock,
} from '@/lib/settings/catalog'
import {
  __resetTimerStore,
  beginSection,
  getTimerSnapshot,
  isSectionInProgress,
  pauseTimer,
  recordAnswer,
  resetSection,
  resetTimer,
  setRemainingQuestions,
  setTimerDuration,
  startTimer,
  subscribeTimer,
} from '@/lib/lsat/timerStore'

const ALL: Dock[] = ['sidebar', 'inspector']

beforeEach(() => {
  __resetTimerStore()
  window.localStorage.clear()
  deleteSettingValue(INSTANCE_SCOPE.id, lsatTimerDock.key)
  deleteSettingValue(INSTANCE_SCOPE.id, lsatTimerVisible.key)
  deleteSettingValue(INSTANCE_SCOPE.id, lsatTimerDuration.key)
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

  it('holds the remaining-question count the pace readout divides by', () => {
    expect(getTimerSnapshot().remainingQuestions).toBeNull()
    setRemainingQuestions(27)
    expect(getTimerSnapshot().remainingQuestions).toBe(27)
    setRemainingQuestions(null)
    expect(getTimerSnapshot().remainingQuestions).toBeNull()
  })

  it('keeps the remaining count through a clock reset but not a new section', () => {
    // Resetting the clock does not change how many questions are in front of
    // you; switching section does, and the panel that knew is gone by then.
    setRemainingQuestions(12)
    resetTimer()
    expect(getTimerSnapshot().remainingQuestions).toBe(12)
    resetSection()
    expect(getTimerSnapshot().remainingQuestions).toBeNull()
  })

  // `beginSection` is the reason `resetSection` above is now reachable at all
  // (BL-20260916-03). The caller that needs it — the static drill — is
  // remounted by its own page on a section switch, so it cannot tell a change
  // of section from a first mount: every ref it might compare against is
  // reinitialised with it. The store is the one participant that is not
  // remounted, so deciding it here is what makes the decision possible.
  describe('beginSection', () => {
    it('claims the clock without resetting the first section', () => {
      // Nothing to carry over yet, and a reader may already have set a preset
      // and pressed Start before the drill mounted.
      startTimer()
      recordAnswer(30)
      expect(beginSection('LR')).toBe(false)
      expect(getTimerSnapshot().section).toBe('LR')
      expect(getTimerSnapshot().answered).toBe(1)
      expect(getTimerSnapshot().running).toBe(true)
    })

    it('is idempotent, so a remount within a section keeps its clock', () => {
      // The property this store was hoisted out of `useState` to provide
      // (BL-20260830-04): moving the widget between docks, or a refresh
      // restoring through `rehydrate`, must not restart a running section.
      beginSection('LR')
      startTimer()
      recordAnswer(45)
      expect(beginSection('LR')).toBe(false)
      expect(getTimerSnapshot().running).toBe(true)
      expect(getTimerSnapshot().answered).toBe(1)
      expect(getTimerSnapshot().answeredSeconds).toBe(45)
    })

    it('resets the clock and the pace counters on a real change of section', () => {
      beginSection('LR')
      startTimer()
      recordAnswer(90)
      setRemainingQuestions(24)

      expect(beginSection('RC')).toBe(true)

      const s = getTimerSnapshot()
      expect(s.section).toBe('RC')
      expect(s.answered).toBe(0)
      expect(s.answeredSeconds).toBe(0)
      expect(s.remainingQuestions).toBeNull()
      expect(s.running).toBe(false)
      expect(s.remainingSeconds).toBe(s.durationSeconds)
    })

    it('leaves a chosen duration alone across the switch', () => {
      // The preset is the reader's choice and outlives a section; the clock
      // returns to `durationSeconds`, not to a hard-coded 35 minutes.
      setTimerDuration(600)
      beginSection('LR')
      recordAnswer(60)
      beginSection('LG')
      expect(getTimerSnapshot().durationSeconds).toBe(600)
      expect(getTimerSnapshot().remainingSeconds).toBe(600)
    })

    it('records the section in the persisted blob, so a refresh is not a switch', () => {
      // If the section were dropped on rehydrate, every reload would look like
      // a change of section and reset the clock this persistence exists to
      // save — the exact bug, reintroduced one layer down.
      beginSection('RC')
      const blob = window.sessionStorage.getItem('law-ai.lsat.timer.v1')
      expect(JSON.parse(blob as string).section).toBe('RC')
    })

    it('notifies subscribers when it claims a section', () => {
      const seen = vi.fn()
      const unsubscribe = subscribeTimer(seen)
      try {
        beginSection('LR')
        expect(seen).toHaveBeenCalled()
      } finally {
        unsubscribe()
      }
    })
  })
})

function zones(onOwnRoute = true) {
  return (
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
    </>
  )
}

function renderDocks(onOwnRoute = true) {
  return render(zones(onOwnRoute))
}

describe('SectionTimerWidget pace readout', () => {
  it('shows seconds-per-question only once a drill publishes a count', () => {
    renderDocks()
    expect(
      screen.queryByLabelText(/time remaining per question/i),
    ).not.toBeInTheDocument()

    act(() => {
      setRemainingQuestions(25)
    })
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('1:24 left / q')

    act(() => {
      setRemainingQuestions(null)
    })
    expect(
      screen.queryByLabelText(/time remaining per question/i),
    ).not.toBeInTheDocument()
  })

  it('blanks the readout when the stack is finished', () => {
    renderDocks()
    act(() => {
      setRemainingQuestions(0)
    })
    expect(
      screen.queryByLabelText(/time remaining per question/i),
    ).not.toBeInTheDocument()
  })
})

describe('SectionTimerWidget drill presets', () => {
  function openMenu() {
    fireEvent.click(
      screen.getByRole('button', { name: /section timer options/i }),
    )
  }

  it('offers 5 / 10 / 35 minute drills, with 35 the default', () => {
    renderDocks()
    openMenu()
    const presets = screen
      .getAllByRole('menuitemradio')
      .filter((b) => /\d+ min/.test(b.textContent ?? ''))
    expect(presets.map((b) => b.textContent?.replace('✓', ''))).toEqual([
      '5 min',
      '10 min',
      '35 min',
    ])
    expect(
      screen.getByRole('menuitemradio', { name: '35 min' }),
    ).toHaveAttribute('aria-checked', 'true')
  })

  it('resets the clock to the chosen length and remembers the choice', () => {
    renderDocks()
    openMenu()
    fireEvent.click(screen.getByRole('menuitemradio', { name: '10 min' }))

    expect(screen.getByRole('timer')).toHaveTextContent('10:00')
    expect(getTimerSnapshot().durationSeconds).toBe(600)
    // Persisted like the dock is, so a homework length survives a reload.
    expect(
      listSettingValues().find((r) => r.key === lsatTimerDuration.key)?.value,
    ).toBe('10')
  })

  it('paces against the shorter clock, not the full section', () => {
    renderDocks()
    openMenu()
    fireEvent.click(screen.getByRole('menuitemradio', { name: '10 min' }))
    act(() => {
      setRemainingQuestions(5)
    })
    expect(
      screen.getByLabelText(/time remaining per question/i),
    ).toHaveTextContent('2:00 left / q')
  })

  it('refuses to change length while a section is in progress', () => {
    vi.useFakeTimers()
    renderDocks()
    act(() => {
      startTimer()
      vi.advanceTimersByTime(2000)
      pauseTimer()
    })
    openMenu()
    // A started-then-paused section still counts as in progress: the clock
    // holds time the student has spent, and 5 minutes must not eat it.
    expect(screen.getByRole('menuitemradio', { name: '5 min' })).toBeDisabled()
    expect(screen.getByRole('menuitemradio', { name: '35 min' })).toBeDisabled()
  })
})

describe('SectionTimerWidget docking', () => {
  it('docks in the sidebar by default and nowhere else', () => {
    renderDocks()
    const timers = screen.getAllByTestId('lsat-timer')
    expect(timers).toHaveLength(1)
    expect(timers[0]).toHaveAttribute('data-dock', 'sidebar')
  })

  it('moves to the dock chosen from its own menu', () => {
    renderDocks()
    fireEvent.click(screen.getByRole('button', { name: /section timer options/i }))
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

    fireEvent.click(screen.getByRole('button', { name: /section timer options/i }))
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
    fireEvent.click(screen.getByRole('button', { name: /section timer options/i }))
    expect(screen.getByRole('menuitemradio', { name: /Sidebar/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(
      screen.getByRole('menuitemradio', { name: /Inspector/ }),
    ).toHaveAttribute('aria-checked', 'false')
  })
})

describe('SectionTimerWidget visibility (spec 051)', () => {
  it('hides an idle clock by preference but never a running one', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: lsatTimerVisible.key,
      value: false,
      locked: false,
    })
    const { rerender } = renderDocks()
    expect(screen.queryByTestId('lsat-timer')).not.toBeInTheDocument()

    act(() => {
      startTimer()
    })
    rerender(zones())
    // Spec 043 FR-5 still holds: a section in progress shows its clock.
    expect(screen.getByTestId('lsat-timer')).toBeInTheDocument()
  })

  it('offers the same choice from its own menu', () => {
    renderDocks()
    fireEvent.click(screen.getByRole('button', { name: /section timer options/i }))
    const row = screen.getByRole('menuitemcheckbox', { name: /Show when idle/ })
    expect(row).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(row)
    expect(screen.queryByTestId('lsat-timer')).not.toBeInTheDocument()
  })
})
