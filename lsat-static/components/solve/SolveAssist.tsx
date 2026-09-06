'use client'

import { useMemo, useState } from 'react'

import { guideFor } from '@/lib/data'
import type { SolveStep, StepKind } from '@/lib/types'
import Representation from './diagrams/Representation'
import { useShortcuts } from '@/lib/keyboard'

/**
 * Progressive solve-guide reveal as a carousel — the static counterpart of the
 * platform's `frontend/components/lsat/SolveAssist.tsx` (spec 045), ported by
 * spec 046 so the published site teaches the same way the API-backed lab does.
 *
 * Two deliberate differences, both forced by having no server:
 *
 *  1. The guide is read synchronously from the bundle (`guideFor`) instead of
 *     fetched, so there is no loading, error, or retry state.
 *  2. Spoiler steps ship in the bundle — as the answer keys already do, since
 *     the site grades offline — and are locked *client-side* until the question
 *     is graded, mirroring the API's `public_guide_view`. A locked step still
 *     shows its title and position, so the user can see how many steps exist.
 *
 * There is no AI-tutor fallback here; that needs a backend.
 */

const KIND_LABEL: Record<StepKind, string> = {
  orient: 'Orient',
  inventory: 'Inventory',
  symbolize: 'Symbolize',
  diagram: 'Diagram',
  infer: 'Infer',
  eliminate: 'Eliminate',
  answer: 'Answer',
}

// Session-scoped memory of how far each question's guide was revealed.
const revealedByQuestion = new Map<string, number>()

/**
 * Test hook: clear the session's revealed-depth memory.
 *
 * Named for the platform's identical export, so the shared carousel contract
 * (`__tests__/contracts/solveAssist.contract.ts`) can reset either product
 * through the same harness field (BL-20260831-22).
 */
export function resetSolveAssistSession(): void {
  revealedByQuestion.clear()
}

function StepSlide({
  step,
  locked,
  index,
  total,
}: {
  step: SolveStep
  locked: boolean
  index: number
  total: number
}) {
  return (
    <div
      role="group"
      aria-roledescription="slide"
      aria-label={`Step ${index + 1} of ${total}: ${step.title}`}
      className="solve-slide"
    >
      <p className="solve-slide-head">
        <span className="solve-slide-num">{index + 1}</span>
        <span className="solve-slide-kind">{KIND_LABEL[step.kind]}</span>
        <span className="solve-slide-title">{step.title}</span>
      </p>
      {locked ? (
        <p className="solve-locked">
          🔒 Locked — submit an answer first, then reveal the final step.
        </p>
      ) : (
        <>
          {step.text && <p className="solve-slide-text">{step.text}</p>}
          {step.representation && (
            <div className="solve-slide-rep">
              <Representation rep={step.representation} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function SolveAssist({
  questionId,
  graded,
}: {
  questionId: string
  graded: boolean
}) {
  const guide = useMemo(() => guideFor(questionId), [questionId])
  const [revealed, setRevealed] = useState(
    () => revealedByQuestion.get(questionId) ?? 0,
  )
  const [active, setActive] = useState(() =>
    Math.max(0, (revealedByQuestion.get(questionId) ?? 0) - 1),
  )

  const stepCount = guide?.steps.length ?? 0

  // Hints without reaching for the mouse: H opens the guide and then walks it
  // forward, J and K move through what is already revealed, R jumps to the
  // final step once the question has been graded. Declared before the
  // guide-less early return so the hook order never changes between renders.
  useShortcuts({
    h: () => {
      if (!guide) return
      if (revealed === 0) return setRevealedTo(1)
      if (active < revealed - 1) return setActive((a) => a + 1)
      if (revealed < stepCount) return setRevealedTo(revealed + 1)
    },
    k: () => {
      if (guide && active < revealed - 1) setActive((a) => a + 1)
    },
    j: () => {
      if (guide) setActive((a) => Math.max(0, a - 1))
    },
    r: () => {
      if (guide && graded) setRevealedTo(stepCount)
    },
  })

  if (!guide) {
    // The platform offers the AI tutor here instead. Saying so is the point:
    // this is exactly where the absence is felt, and a reader who has just
    // been told "no guide" should learn that the walkthrough exists elsewhere
    // rather than assume nothing was ever written (BL-20260831-25).
    return (
      <p className="solve-none">
        No step-by-step guide for this question yet. This site has no AI tutor
        to ask instead — that needs a server; see the explanation after you
        answer.
      </p>
    )
  }

  const isLocked = (s: SolveStep) => s.spoiler && !graded
  const hasLockedVisible = guide.steps
    .slice(0, revealed)
    .some((s) => isLocked(s))

  const setRevealedTo = (n: number) => {
    const next = Math.min(Math.max(n, 0), stepCount)
    revealedByQuestion.set(questionId, next)
    setRevealed(next)
    setActive(Math.max(0, next - 1))
  }

  const frontier = revealed - 1
  const nextWillReveal = active === frontier && revealed < stepCount
  const canGoNext = active < frontier || nextWillReveal
  const currentStep = revealed > 0 && active < revealed ? guide.steps[active] : null

  return (
    <section aria-label="Solve assist" className="solve">
      <div className="solve-controls">
        {revealed === 0 && (
          <button
            type="button"
            className="btn btn-hint"
            aria-keyshortcuts="H"
            onClick={() => setRevealedTo(1)}
          >
            💡 Hint
          </button>
        )}
        {graded && hasLockedVisible && (
          <button
            type="button"
            className="btn btn-reveal"
            aria-keyshortcuts="R"
            onClick={() => setRevealedTo(stepCount)}
          >
            Show final step
          </button>
        )}
        {revealed > 0 && (
          <span className="solve-progress">
            {guide.method} · step {Math.min(active + 1, stepCount)} of {stepCount}
          </span>
        )}
      </div>

      {currentStep && (
        <div
          role="region"
          aria-roledescription="carousel"
          aria-label="Solve guide steps"
          className="solve-carousel"
        >
          <div aria-live="polite">
            <StepSlide
              step={currentStep}
              locked={isLocked(currentStep)}
              index={active}
              total={stepCount}
            />
          </div>
          <div className="solve-nav">
            <button
              type="button"
              className="btn"
              aria-label="Previous step"
              onClick={() => setActive((a) => Math.max(0, a - 1))}
              disabled={active === 0}
            >
              ‹ Back
            </button>
            <div className="solve-dots">
              {guide.steps.map((s, i) =>
                i < revealed ? (
                  <button
                    key={i}
                    type="button"
                    aria-label={`Go to step ${i + 1}`}
                    aria-current={i === active ? 'step' : undefined}
                    onClick={() => setActive(i)}
                    className={'solve-dot' + (i === active ? ' solve-dot-active' : '')}
                  />
                ) : (
                  <span key={i} aria-hidden="true" className="solve-dot solve-dot-empty" />
                ),
              )}
            </div>
            <button
              type="button"
              className={'btn' + (nextWillReveal ? ' btn-hint' : '')}
              onClick={() => {
                if (active < frontier) setActive((a) => a + 1)
                else if (nextWillReveal) setRevealedTo(revealed + 1)
              }}
              disabled={!canGoNext}
            >
              {nextWillReveal ? '💡 Next hint ›' : 'Next ›'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
