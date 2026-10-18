/**
 * What a section switch does to the clock (BL-20260916-03).
 *
 * `lib/lsat/timerStore.ts` is module-level on purpose: the clock has to
 * survive a remount and a refresh, or a dockable timer would restart a running
 * 35-minute section every time it moved (BL-20260830-04). The cost of that is
 * the case here — the counters also survive a switch to a *different* section,
 * which is the one time none of it should carry over. `resetSection()` was
 * written for exactly this and `Drill` called it, but the call was unreachable:
 * the guard around it compared `useRef(section)` against `section`, and
 * `app/page.tsx` keys the view wrapper on `view`, so a switch remounts the
 * drill and reinitialises that ref to the new section. Always equal, always an
 * early return, never a reset. RC inherited LR's clock; LG inherited RC's
 * average.
 *
 * Every case therefore **unmounts and remounts** rather than re-rendering with
 * a new prop, because that is what the page really does — and it is precisely
 * what `__tests__/Drill.test.tsx` never did. Its eight cases are all
 * `render(<Drill section="LR" />)`, so the suite could prove the store
 * primitive works (`SectionTimer.test.tsx` calls `resetSection()` directly)
 * while never exercising the wiring that was broken.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Drill from '@/components/Drill'
import { identityOrder, presetOrder, resetOrders } from '@/lib/shuffle'
import {
  __resetTimerStore,
  getTimerSnapshot,
  setTimerDuration,
  startTimer,
} from '@/lib/lsat/timerStore'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    questionsFor: () => f.QUESTIONS,
    sectionMeta: () => f.SECTION_LR,
    passageById: () => undefined,
    guideFor: () => undefined,
    playbookFor: () => undefined,
    conceptById: () => undefined,
  }
})

/** Answer the question on screen and grade it, billing the section clock. */
function answerOne(letter: string): void {
  fireEvent.keyDown(window, { key: letter })
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
}

function average(): HTMLElement | null {
  return screen.queryByLabelText(/average time per question/i)
}

describe('switching sections', () => {
  beforeEach(() => {
    __resetTimerStore()
    resetOrders()
    for (const id of ['lr-fixture-01', 'lr-fixture-02', 'lr-fixture-03']) {
      presetOrder(id, identityOrder(5))
    }
  })

  afterEach(() => {
    __resetTimerStore()
  })

  it('clears the pace counters when the next section mounts', () => {
    // The criterion from the report, literally: answer in LR, replace the
    // drill the way `key={view}` does, and the new section must start clean.
    const lr = render(<Drill section="LR" />)
    answerOne('c')
    expect(getTimerSnapshot().answered).toBe(1)
    expect(getTimerSnapshot().answeredSeconds).toBeGreaterThanOrEqual(0)

    lr.unmount()
    render(<Drill section="RC" />)

    expect(getTimerSnapshot().answered).toBe(0)
    expect(getTimerSnapshot().answeredSeconds).toBe(0)
    expect(getTimerSnapshot().section).toBe('RC')
  })

  it('shows the next section a full clock and no inherited average', () => {
    const lr = render(<Drill section="LR" />)
    act(() => {
      startTimer()
    })
    answerOne('c')
    expect(average()).toBeInTheDocument()

    lr.unmount()
    render(<Drill section="RC" />)

    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(average()).not.toBeInTheDocument()
    expect(getTimerSnapshot().running).toBe(false)
  })

  it('does not carry an average on down the chain, RC to LG', () => {
    // The second half of the report: LG inherited RC's average, not LR's.
    const lr = render(<Drill section="LR" />)
    answerOne('c')
    lr.unmount()

    const rc = render(<Drill section="RC" />)
    answerOne('a')
    expect(average()).toBeInTheDocument()
    rc.unmount()

    render(<Drill section="LG" />)
    expect(average()).not.toBeInTheDocument()
    expect(getTimerSnapshot().answered).toBe(0)
  })

  it('keeps a running clock across a remount within the same section', () => {
    // The property the module store exists for, and the one this fix must not
    // cost: a remount that is NOT a section change keeps everything.
    vi.useFakeTimers()
    try {
      const first = render(<Drill section="LR" />)
      act(() => {
        startTimer()
        vi.advanceTimersByTime(3000)
      })
      answerOne('c')
      const before = getTimerSnapshot()
      expect(before.running).toBe(true)
      expect(before.remainingSeconds).toBe(2097) // 35:00 - 3s

      first.unmount()
      render(<Drill section="LR" />)

      const after = getTimerSnapshot()
      expect(after.running).toBe(true)
      expect(after.remainingSeconds).toBe(2097)
      expect(after.answered).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not reset a clock the reader started before opening a drill', () => {
    // The first section claimed on a page has nothing to carry over. Setting a
    // preset and pressing Start, then opening a drill, must not throw that
    // away — `beginSection` only resets on an actual *change*.
    act(() => {
      setTimerDuration(10 * 60)
      startTimer()
    })
    render(<Drill section="LR" />)

    expect(getTimerSnapshot().running).toBe(true)
    expect(getTimerSnapshot().durationSeconds).toBe(600)
    expect(getTimerSnapshot().section).toBe('LR')
  })

  it('keeps a chosen duration preset across the switch', () => {
    // `resetSection` returns the clock to `durationSeconds`, not to 35:00 —
    // the preset is the reader's choice and outlives the section.
    const lr = render(<Drill section="LR" />)
    fireEvent.click(
      within(screen.getByRole('radiogroup', { name: 'Drill length' })).getByRole(
        'radio',
        { name: '10 min' },
      ),
    )
    answerOne('c')
    lr.unmount()

    render(<Drill section="RC" />)
    expect(getTimerSnapshot().durationSeconds).toBe(600)
    expect(screen.getByRole('timer')).toHaveTextContent('10:00')
  })

  it('leaves the Reset button preserving the answered count', () => {
    // `resetTimer` !== `resetSection`, per the docstrings. A learner who
    // resets the clock mid-drill has still answered what they answered, and
    // this fix must not quietly merge the two.
    render(<Drill section="LR" />)
    answerOne('c')
    expect(getTimerSnapshot().answered).toBe(1)

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))

    expect(getTimerSnapshot().answered).toBe(1)
    expect(average()).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
  })

  it('restarts the drill itself on the new section', () => {
    // The other half of what the old guard was meant to do: index, answers and
    // the move counter all start over, and arriving must not steal focus.
    const lr = render(<Drill section="LR" />)
    answerOne('c')
    fireEvent.keyDown(window, { key: 'n' })
    expect(screen.getByRole('article')).toHaveAccessibleName('Question 2 of 3')
    lr.unmount()

    render(<Drill section="RC" />)
    expect(screen.getByRole('article')).toHaveAccessibleName('Question 1 of 3')
    expect(document.activeElement).toBe(document.body)
  })
})
