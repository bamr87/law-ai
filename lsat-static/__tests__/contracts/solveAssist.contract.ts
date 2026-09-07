/**
 * One behavioural contract for the hint carousel, run against both products
 * (BL-20260831-22).
 *
 * `SolveAssist` exists twice — `frontend/components/lsat/SolveAssist.tsx` over
 * the API, and `lsat-static/components/solve/SolveAssist.tsx` over the bundled
 * `content.json`. `ux_audit.py` R13 checks only that both files exist, and the
 * root suite compares their source structurally; neither says the two *behave*
 * alike. This does: the cases below are written against the accessible DOM —
 * slide groups, the hint affordances, the step dots, the locked stub — which
 * is the part that must not diverge, and is the part a reader actually meets.
 *
 * Everything product-specific goes in the harness: how the carousel is
 * mounted, how long a reveal takes, and how a graded reader gets at the
 * spoiler. Deliberate divergences (the platform's AI-tutor fallback, the
 * static site's keyboard bindings) stay in each product's own suite.
 *
 * This file is a committed mirror, refreshed by `make ui-sync` and drift-gated
 * by ux_audit R12 — the static export cannot import across the repo root, so a
 * copy is the workable answer and an unchecked copy is a fork with extra
 * steps.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

export interface SolveAssistHarness {
  /** Names the product in the test output: "platform" / "static site". */
  product: string
  /**
   * Mount the carousel for a question that HAS a guide, and hand back a way
   * to change `graded` without remounting — grading mid-question is exactly
   * the transition the spoiler lock turns on. One mount at a time: a harness
   * that is called twice must replace the first render, not add to it.
   */
  mount(graded: boolean): { setGraded(graded: boolean): void }
  /**
   * The guide's steps in order. The last one is the spoiler: its `text` must
   * not be readable before the question is graded.
   */
  steps: { title: string; text: string }[]
  /** Clear session-scoped reveal depth. Both products keep it module-level. */
  reset(): void
  /**
   * True where a graded reader must still ask for the spoiler — the platform
   * refetches behind "Show final step", because the server never sent the
   * locked text. False where the text was in the bundle all along and the
   * lock lifts with `graded`.
   */
  unlockNeedsButton: boolean
}

const HINT = /^💡 hint$/i
const NEXT_HINT = /next hint/i
const LOCKED = /locked — submit an answer/i

function slide(): HTMLElement {
  return screen.getByRole('group')
}

const DOT = { name: /^go to step /i } as const

function dots(): HTMLElement[] {
  return screen.getAllByRole('button', DOT)
}

/**
 * Assert the shared reveal contract against one product.
 *
 * Call it from that product's own SolveAssist suite; it declares its own
 * `describe`, so the two suites can each keep their product-specific cases
 * alongside.
 */
export function describeSolveAssistContract(h: SolveAssistHarness): void {
  const total = h.steps.length
  const spoiler = h.steps[total - 1]

  /**
   * Reveal `times` further steps, one at a time.
   *
   * Two things are product-agnostic here and both are part of the contract:
   * the affordance renames itself once the guide is open ("💡 Hint" becomes
   * "💡 Next hint ›"), and every reveal adds exactly one dot. The dot count is
   * therefore also the settle signal — the platform fetches each step, so
   * clicking again before the last one landed would be dropped by its
   * in-flight guard, and the static site simply satisfies it immediately.
   */
  async function reveal(times = 1): Promise<void> {
    for (let i = 0; i < times; i += 1) {
      const before = screen.queryAllByRole('button', DOT).length
      const first = screen.queryByRole('button', { name: HINT })
      fireEvent.click(first ?? screen.getByRole('button', { name: NEXT_HINT }))
      await waitFor(() =>
        expect(screen.queryAllByRole('button', DOT)).toHaveLength(before + 1),
      )
    }
  }

  describe(`SolveAssist carousel contract (${h.product})`, () => {
    beforeEach(() => {
      h.reset()
    })

    it('reveals one step per hint, one slide on screen at a time', async () => {
      h.mount(false)
      // Nothing is revealed until the reader asks: a guide that opened itself
      // would hand out the method before they had tried the question.
      expect(screen.queryByRole('group')).toBeNull()

      await reveal()
      expect(screen.getAllByRole('group')).toHaveLength(1)
      expect(slide()).toHaveAccessibleName(`Step 1 of ${total}: ${h.steps[0].title}`)
      expect(screen.getByText(h.steps[0].text)).toBeInTheDocument()
      expect(screen.getByText(new RegExp(`step 1 of ${total}`, 'i'))).toBeInTheDocument()

      await reveal()
      // A carousel, not a growing stack: step 1 has left the DOM.
      expect(screen.getAllByRole('group')).toHaveLength(1)
      expect(screen.queryByText(h.steps[0].text)).toBeNull()
      expect(screen.getByText(h.steps[1].text)).toBeInTheDocument()
      expect(screen.getByText(new RegExp(`step 2 of ${total}`, 'i'))).toBeInTheDocument()
    })

    it('walks back and forward through revealed steps without revealing more', async () => {
      h.mount(false)
      await reveal(2)
      expect(dots()).toHaveLength(2)

      fireEvent.click(screen.getByRole('button', { name: /previous step/i }))
      expect(screen.getByText(h.steps[0].text)).toBeInTheDocument()
      // At the first slide there is nowhere back to go.
      expect(screen.getByRole('button', { name: /previous step/i })).toBeDisabled()

      // Forward inside what is already open is plain Next, not a new hint.
      fireEvent.click(screen.getByRole('button', { name: /^next ›$/i }))
      expect(screen.getByText(h.steps[1].text)).toBeInTheDocument()
      expect(dots()).toHaveLength(2)
    })

    it('jumps straight to a revealed step from its dot', async () => {
      h.mount(false)
      await reveal(2)
      fireEvent.click(dots()[0])
      expect(slide()).toHaveAccessibleName(`Step 1 of ${total}: ${h.steps[0].title}`)
      expect(dots()[0]).toHaveAttribute('aria-current', 'step')
      expect(dots()[1]).not.toHaveAttribute('aria-current')
    })

    it('shows a spoiler step as a locked stub until the question is graded', async () => {
      h.mount(false)
      await reveal(total)

      // The step's position and title are visible — you can see how many
      // steps there are — but its content is not.
      expect(slide()).toHaveAccessibleName(`Step ${total} of ${total}: ${spoiler.title}`)
      expect(within(slide()).getByText(LOCKED)).toBeInTheDocument()
      expect(screen.queryByText(spoiler.text)).toBeNull()
      // Nothing left to reveal, and no way round the lock while ungraded.
      expect(screen.queryByRole('button', { name: NEXT_HINT })).toBeNull()
      expect(screen.queryByRole('button', { name: /show final step/i })).toBeNull()
    })

    it('unlocks the spoiler once the question is graded', async () => {
      const handle = h.mount(false)
      await reveal(total)
      handle.setGraded(true)
      if (h.unlockNeedsButton) {
        fireEvent.click(screen.getByRole('button', { name: /show final step/i }))
      }
      await waitFor(() =>
        expect(screen.getByText(spoiler.text)).toBeInTheDocument(),
      )
      expect(screen.queryByText(LOCKED)).toBeNull()
      expect(slide()).toHaveAccessibleName(`Step ${total} of ${total}: ${spoiler.title}`)
    })

    it('stops at the last step rather than offering a reveal that does nothing', async () => {
      h.mount(false)
      await reveal(total)
      expect(dots()).toHaveLength(total)
      expect(screen.queryByRole('button', { name: HINT })).toBeNull()
      expect(screen.queryByRole('button', { name: NEXT_HINT })).toBeNull()
      expect(screen.getByRole('button', { name: /^next ›$/i })).toBeDisabled()
    })
  })
}
