/**
 * Keeping your place in a section across a detour (BL-20260916-01).
 *
 * `app/page.tsx` wraps the view switch in `<div className="view-anim"
 * key={view}>`, which is an instruction to React to throw the subtree away and
 * build a new one whenever the destination changes. The drill kept its
 * position and its answers in component `useState`, so checking Stats
 * mid-section — the one thing Stats exists to be used for — silently dropped
 * the reader back on question 1 with their selections gone.
 *
 * What made it a bug rather than a design choice is that the site disagreed
 * with itself. Three tiers of state cross that detour and only the drill's was
 * lost: attempts live in `localStorage` (`lib/progress.ts`) and the section
 * clock lives in a module store (`lib/lsat/timerStore.ts`), so Stats went on
 * showing two attempted questions while the drill claimed none had been
 * answered.
 *
 * Every case here renders `Page`, not `Drill`, because the remount is the
 * parent's doing: a `Drill` rendered on its own never unmounts, which is
 * exactly why `__tests__/Drill.test.tsx` — eight cases, all
 * `render(<Drill section="LR" />)` — could pass while this was broken.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'
import { identityOrder, presetOrder, resetOrders } from '@/lib/shuffle'
import { __resetTimerStore, getTimerSnapshot } from '@/lib/lsat/timerStore'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

function go(destination: string): void {
  fireEvent.click(screen.getByRole('button', { name: destination }))
}

function card(): HTMLElement {
  return screen.getByRole('article')
}

function checked(): string[] {
  return within(screen.getByRole('radiogroup', { name: 'Answer choices' }))
    .getAllByRole('radio')
    .filter((r) => r.getAttribute('aria-checked') === 'true')
    .map((r) => r.textContent?.trim().charAt(0) ?? '')
}

function press(key: string): void {
  fireEvent.keyDown(window, { key })
}

/**
 * Answer the question on screen with `letter` and grade it.
 *
 * Deliberately graded with the button rather than `Enter`. `Enter` works on
 * the first question of a section and silently stops working on every one
 * after it, which is a *different* defect and one this suite must not depend
 * on: Drill's window listener outlives QuestionCard's, so once the card has
 * been remounted for a new question Drill's `Enter` binding is registered
 * first, claims the keystroke with `preventDefault()` (`lib/keyboard.ts`
 * treats a claimed event as handled), and then no-ops because the question is
 * not yet answered. Filed as BL-20260916-02; the letter keys and the button
 * are both unaffected.
 */
function answer(letter: string): void {
  press(letter)
  fireEvent.click(screen.getByRole('button', { name: 'Check answer' }))
}

/** Move to the next question the way the drill nav does. */
function next(): void {
  fireEvent.click(
    within(screen.getByRole('navigation', { name: 'Question navigation' })).getByRole(
      'button',
      { name: /Next/ },
    ),
  )
}

describe('a drill position across a view change', () => {
  beforeEach(() => {
    // The clock is a module store and survives `cleanup()` by design; reset it
    // so a case asserts its own section rather than the previous case's.
    __resetTimerStore()
    // Choices are shuffled per attempt (BL-20260606-01). This suite is about
    // what survives a remount, not about the shuffle, so pin the identity
    // order and keep asserting on the bank's own labels.
    resetOrders()
    for (const id of ['lr-fixture-01', 'lr-fixture-02', 'lr-fixture-03']) {
      presetOrder(id, identityOrder(5))
    }
  })

  it('restores the item index, the selection and the feedback after Stats', () => {
    // The reported bug, end to end. Before the fix this came back as
    // "Question 1 of 3" with nothing checked and no Explanation region.
    render(<Page />)
    go('Logical Reasoning')

    answer('c') // grades question 1
    next()
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    answer('a') // grades question 2
    expect(screen.getByRole('region', { name: 'Explanation' })).toBeInTheDocument()

    go('Stats')
    expect(screen.queryByRole('article')).toBeNull()
    go('Logical Reasoning')

    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(checked()).toEqual(['A'])
    expect(screen.getByRole('region', { name: 'Explanation' })).toHaveTextContent(
      'Explanation 2.',
    )
  })

  it('leaves Stats and the drill agreeing about what was answered', () => {
    // The disagreement is the part a reader can actually see: two attempts on
    // the Stats table, and a drill insisting they had answered nothing.
    render(<Page />)
    go('Logical Reasoning')
    answer('c')
    next()
    answer('a')

    go('Stats')
    const row = screen.getByRole('row', { name: /Logical Reasoning/ })
    const cells = within(row).getAllByRole('cell')
    // correct / attempted / accuracy
    expect(cells[1]).toHaveTextContent('2')

    go('Logical Reasoning')
    // Two questions answered, and the drill knows about both of them: the one
    // it is showing, and the one it can page back to.
    expect(checked()).toEqual(['A'])
    press('p')
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(checked()).toEqual(['C'])
  })

  it('keeps the section clock running across the detour', () => {
    // Pinned deliberately: the timer's survival is the *correct* behaviour
    // (timerStore.ts:1-24, BL-20260830-04) and the fix must not reach over and
    // couple the drill's restore to it.
    render(<Page />)
    go('Logical Reasoning')
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(getTimerSnapshot().running).toBe(true)

    go('Stats')
    go('Logical Reasoning')
    expect(getTimerSnapshot().running).toBe(true)
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
  })

  it('does not steal focus out of the nav when it restores', () => {
    // `moves` is what tells the focus effect that *the user* moved. Restoring
    // a position is not a move, and bumping it would land focus on the card
    // while the reader was still on the nav button they just clicked — the
    // regression `Drill.test.tsx` pins for mounting.
    render(<Page />)
    go('Logical Reasoning')
    answer('c')
    next()

    go('Stats')
    const navButton = screen.getByRole('button', { name: 'Logical Reasoning' })
    fireEvent.click(navButton)
    expect(card()).toHaveAccessibleName('Question 2 of 3')
    expect(document.activeElement).not.toBe(card())
  })

  it('starts a different section clean rather than showing the last one', () => {
    // The reset `Drill.tsx:55-62` intended, preserved: the record is keyed per
    // section, so RC reads RC's place — and a section never opened has none.
    render(<Page />)
    go('Logical Reasoning')
    answer('c')
    next()
    expect(card()).toHaveAccessibleName('Question 2 of 3')

    go('Reading Comprehension')
    expect(card()).toHaveAccessibleName('Question 1 of 3')
    expect(checked()).toEqual([])
    expect(screen.queryByRole('region', { name: 'Explanation' })).toBeNull()

    // ...and LR is still where it was left, which is the whole point.
    go('Logical Reasoning')
    expect(card()).toHaveAccessibleName('Question 2 of 3')
  })

  it('reads fine when storage is blocked', () => {
    // Private browsing and blocked site data both throw on access. A position
    // is a convenience; losing it must cost the reader nothing but the
    // position (`lib/deviceState.ts` header).
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      render(<Page />)
      go('Logical Reasoning')
      answer('c')
      next()
      expect(card()).toHaveAccessibleName('Question 2 of 3')
      go('Stats')
      go('Logical Reasoning')
      // No saved position to read, so the drill starts over — but it renders.
      expect(card()).toHaveAccessibleName('Question 1 of 3')
    } finally {
      get.mockRestore()
      set.mockRestore()
    }
  })
})
