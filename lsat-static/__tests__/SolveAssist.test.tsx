/**
 * Hint-carousel keys on the static site (BL-20260901-07).
 *
 * `H` reveals forward, `J`/`K` walk what is already revealed without revealing
 * more, and `R` jumps to the end only once the question is graded — the same
 * reveal discipline the platform carousel keeps, since a spoiler step read
 * before answering destroys the exercise. The static bundle ships every step
 * (there is no server to withhold them), so the lock is enforced here, in the
 * UI, and that is what these tests press on.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import SolveAssist, {
  resetSolveAssistSession,
} from '@/components/solve/SolveAssist'
import { describeSolveAssistContract } from './contracts/solveAssist.contract'
import { GUIDE } from './fixtures'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    // The module keeps reveal depth per question id, so each test uses its own.
    guideFor: (id: string) => (id.startsWith('no-guide') ? undefined : f.GUIDE),
  }
})

function slide(): HTMLElement {
  return screen.getByRole('group')
}

function dots(): HTMLElement[] {
  return screen.getAllByRole('button', { name: /^Go to step / })
}

function press(key: string, times = 1): void {
  for (let n = 0; n < times; n += 1) fireEvent.keyDown(window, { key })
}

describe('SolveAssist carousel keys', () => {
  it('opens with H and then walks forward one step per press', () => {
    render(<SolveAssist questionId="q-forward" graded={false} />)
    expect(screen.queryByRole('group')).toBeNull()
    expect(screen.getByRole('button', { name: '💡 Hint' })).toBeInTheDocument()

    press('h')
    expect(slide()).toHaveAccessibleName('Step 1 of 4: Read the question stem')
    expect(screen.getByText('Step one text.')).toBeInTheDocument()
    expect(dots()).toHaveLength(1)

    press('h')
    expect(slide()).toHaveAccessibleName('Step 2 of 4: Split premise from conclusion')
    expect(screen.getByText('Step two text.')).toBeInTheDocument()
    expect(dots()).toHaveLength(2)
  })

  it('J and K move through revealed steps without revealing another', () => {
    render(<SolveAssist questionId="q-walk" graded={false} />)
    press('h', 3)
    expect(dots()).toHaveLength(3)
    expect(slide()).toHaveAccessibleName('Step 3 of 4: Name the gap')

    press('j')
    expect(slide()).toHaveAccessibleName('Step 2 of 4: Split premise from conclusion')
    press('j')
    expect(slide()).toHaveAccessibleName('Step 1 of 4: Read the question stem')
    // Back at the first slide, J is inert rather than wrapping.
    press('j')
    expect(slide()).toHaveAccessibleName('Step 1 of 4: Read the question stem')

    press('k')
    expect(slide()).toHaveAccessibleName('Step 2 of 4: Split premise from conclusion')
    // Nothing new was revealed by walking back and forth.
    expect(dots()).toHaveLength(3)

    // K stops at the frontier; only H reveals.
    press('k', 3)
    expect(slide()).toHaveAccessibleName('Step 3 of 4: Name the gap')
    expect(dots()).toHaveLength(3)
  })

  it('keeps the spoiler step locked until the question is graded', () => {
    render(<SolveAssist questionId="q-locked" graded={false} />)
    press('h', 4)
    expect(slide()).toHaveAccessibleName('Step 4 of 4: The answer')
    expect(within(slide()).getByText(/Locked — submit an answer first/)).toBeInTheDocument()
    expect(screen.queryByText('Step four text.')).toBeNull()
    // The lock is not a dead end: there is no "Show final step" until graded.
    expect(screen.queryByRole('button', { name: 'Show final step' })).toBeNull()
  })

  it('R jumps to the final step, but only once the question is graded', () => {
    const { rerender } = render(<SolveAssist questionId="q-reveal" graded={false} />)
    press('r')
    expect(screen.queryByRole('group')).toBeNull()

    rerender(<SolveAssist questionId="q-reveal" graded />)
    press('r')
    expect(slide()).toHaveAccessibleName('Step 4 of 4: The answer')
    expect(screen.getByText('Step four text.')).toBeInTheDocument()
    expect(dots()).toHaveLength(4)
  })

  it('unlocks a revealed spoiler step in place the moment the question is graded', () => {
    // The lock here is computed from `graded`, not baked into the payload the
    // way the API-backed lab's is, so grading opens the step the reader is
    // already looking at — no second reveal, no lost position.
    const { rerender } = render(<SolveAssist questionId="q-unlock" graded={false} />)
    press('h', 4)
    expect(screen.queryByText('Step four text.')).toBeNull()

    rerender(<SolveAssist questionId="q-unlock" graded />)
    expect(slide()).toHaveAccessibleName('Step 4 of 4: The answer')
    expect(screen.getByText('Step four text.')).toBeInTheDocument()
    expect(screen.queryByText(/Locked — submit an answer first/)).toBeNull()
    // ...and so there is no second affordance to press: a "Show final step"
    // button could only render when nothing was locked (BL-20260905-14).
    expect(screen.queryByRole('button', { name: 'Show final step' })).toBeNull()
  })

  it('navigates by dot, marking the current step', () => {
    render(<SolveAssist questionId="q-dots" graded={false} />)
    press('h', 3)
    fireEvent.click(dots()[0])
    expect(slide()).toHaveAccessibleName('Step 1 of 4: Read the question stem')
    expect(dots()[0]).toHaveAttribute('aria-current', 'step')
    expect(dots()[2]).not.toHaveAttribute('aria-current')
  })

  it('says so, and stays inert, when a question has no guide', () => {
    render(<SolveAssist questionId="no-guide-1" graded />)
    const empty = screen.getByText(/No step-by-step guide for this question yet/)
    expect(empty).toBeInTheDocument()
    // Where the platform offers the AI tutor, this site says why it cannot —
    // the absence is felt right here (BL-20260831-25).
    expect(empty).toHaveTextContent('no AI tutor')
    press('h')
    press('r')
    expect(screen.queryByRole('group')).toBeNull()
  })
})

// The half of this carousel that must match the platform's, asserted from the
// same file both products run (BL-20260831-22). The keyboard cases above are
// the static site's own: the published drill has no mouse-only affordance,
// and the platform carousel has no key bindings to compare against.
describeSolveAssistContract({
  product: 'static site',
  steps: GUIDE.steps.map((s) => ({ title: s.title, text: s.text })),
  reset: resetSolveAssistSession,
  // ...which is also why grading unlocks the spoiler step already on screen
  // instead of sending the reader back for a second reveal.
  unlockNeedsButton: false,
  mount(graded) {
    cleanup()
    const view = render(<SolveAssist questionId="q-contract" graded={graded} />)
    return {
      setGraded: (next) =>
        view.rerender(<SolveAssist questionId="q-contract" graded={next} />),
    }
  },
})
