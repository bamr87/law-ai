'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchLsatGuide,
  LsatGuideNotFoundError,
  recordLsatHintReveal,
  type LsatSolveGuide,
  type LsatSolveStep,
} from '@/lib/api'
import Representation from '@/components/lsat/diagrams/Representation'
import { useShortcuts } from '@/lib/lsat/keyboard'

/**
 * Progressive solve-guide reveal, rendered as a carousel (spec 045 FR-6,
 * T-012): one step on screen at a time with back/next navigation and step
 * dots, instead of a growing stack.
 *
 * The hint semantics are unchanged: each *reveal* still exposes exactly one
 * new step, spoiler steps stay locked stubs until the question is graded
 * (then unlock via "Show final step", which refetches with spoilers), and
 * `hints_used` counts revealed content steps. Questions without a guide
 * fall back to the AI tutor (FR-8). Revealed depth persists per question
 * for the session.
 */

const KIND_LABEL: Record<LsatSolveStep['kind'], string> = {
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

/** Test hook: clear the session's revealed-depth memory. */
export function resetSolveAssistSession(): void {
  revealedByQuestion.clear()
}

function StepSlide({
  step,
  index,
  total,
}: {
  step: LsatSolveStep
  index: number
  total: number
}) {
  return (
    <div
      role="group"
      aria-roledescription="slide"
      aria-label={`Step ${index + 1} of ${total}: ${step.title}`}
      className="rounded-lg border border-slate-800 bg-slate-900/40 p-3"
    >
      <p className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="font-mono text-slate-600">{index + 1}</span>
        <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-sky-300">
          {KIND_LABEL[step.kind]}
        </span>
        <span className="normal-case text-slate-300">{step.title}</span>
      </p>
      {step.locked ? (
        <p className="mt-2 text-xs italic text-slate-500">
          🔒 Locked — submit an answer first, then reveal the final step.
        </p>
      ) : (
        <>
          {step.text && (
            <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-300">
              {step.text}
            </p>
          )}
          {step.representation && (
            <div className="mt-3">
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
  onHintsUsedChange,
  onAskTutor,
  remap,
}: {
  questionId: string
  graded: boolean
  onHintsUsedChange?: (hintsUsed: number) => void
  onAskTutor?: () => void
  /** The serve's shuffle token, so the steps name the labels on screen. */
  remap?: string
}) {
  // Mounted with key={questionId}, so state resets per question; the
  // initializers restore this session's revealed depth (FR-6).
  const [guide, setGuide] = useState<LsatSolveGuide | null>(null)
  const [revealed, setRevealed] = useState(
    () => revealedByQuestion.get(questionId) ?? 0,
  )
  const [active, setActive] = useState(() =>
    Math.max(0, (revealedByQuestion.get(questionId) ?? 0) - 1),
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [noGuide, setNoGuide] = useState<{ hasTutor: boolean } | null>(null)
  const fetchingRef = useRef(false)

  const loadGuide = useCallback(
    async (spoilers: boolean): Promise<LsatSolveGuide | null> => {
      if (fetchingRef.current) return null
      fetchingRef.current = true
      setLoading(true)
      setError(null)
      try {
        // A shuffled serve moves the labels the steps name, so the guide is
        // fetched under the same permutation (BL-20260606-01).
        const g = await fetchLsatGuide(questionId, { spoilers, remap })
        setGuide(g)
        return g
      } catch (e) {
        if (e instanceof LsatGuideNotFoundError) {
          setNoGuide({ hasTutor: e.hasTutor })
        } else {
          setError(e instanceof Error ? e.message : 'Guide fetch failed')
        }
        return null
      } finally {
        fetchingRef.current = false
        setLoading(false)
      }
    },
    [questionId, remap],
  )

  // Restore previously revealed steps after a question switch.
  useEffect(() => {
    if (revealed > 0 && !guide && !noGuide && !loading) {
      void loadGuide(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealed, guide, noGuide, loadGuide])

  // Hints used = revealed steps whose content is visible (locked stubs are
  // not help). Reported upward for grade-time `hints_used`.
  const hintsUsed = useMemo(
    () =>
      guide ? guide.steps.slice(0, revealed).filter((s) => !s.locked).length : 0,
    [guide, revealed],
  )
  useEffect(() => {
    onHintsUsedChange?.(hintsUsed)
  }, [hintsUsed, onHintsUsedChange])

  // Per-reveal analytics (BL-20260830-13). Fire-and-forget in the strictest
  // sense: the promise is not awaited and its rejection is swallowed, because
  // a hint that failed to be *counted* is still a hint the learner has.
  const noteReveal = useCallback(
    (stepIndex: number, revealedCount: number, spoiler = false) => {
      void recordLsatHintReveal(questionId, {
        stepIndex,
        revealedCount,
        spoiler,
      }).catch(() => {
        /* never surfaced: the reveal already happened */
      })
    },
    [questionId],
  )

  // The revealed depth, readable from an async handler. `reveal` awaits a
  // fetch before it decides, so the `revealed` it closed over may be stale by
  // then — and a state updater has to stay pure, which the analytics call
  // inside one would not be.
  const revealedRef = useRef(revealed)
  useEffect(() => {
    revealedRef.current = revealed
  })

  const reveal = async () => {
    const g = guide ?? (await loadGuide(false))
    if (!g) return
    const current = revealedRef.current
    const next = Math.min(current + 1, g.step_count)
    if (next === current) return
    revealedRef.current = next
    revealedByQuestion.set(questionId, next)
    setRevealed(next)
    setActive(next - 1)
    noteReveal(next - 1, next, Boolean(g.steps[next - 1]?.spoiler))
  }

  const showFinal = async () => {
    const g = await loadGuide(true)
    if (!g) return
    revealedRef.current = g.step_count
    setRevealed(g.step_count)
    setActive(g.step_count - 1)
    revealedByQuestion.set(questionId, g.step_count)
    // "Show final step" unlocks the spoiler, whatever depth it was at.
    noteReveal(g.step_count - 1, g.step_count, true)
  }

  const revealedSteps = guide ? guide.steps.slice(0, revealed) : []
  const hasLockedVisible = revealedSteps.some((s) => s.locked)
  const frontier = revealed - 1
  const nextWillReveal =
    guide !== null && active === frontier && revealed < guide.step_count
  const canGoNext = guide !== null && (active < frontier || nextWillReveal)
  const currentStep =
    guide && revealed > 0 && active < revealed ? guide.steps[active] : null

  const goNext = () => {
    if (!guide) return
    if (active < frontier) {
      setActive((a) => a + 1)
    } else if (nextWillReveal) {
      void reveal()
    }
  }

  // Hint keys, the static site's contract ported (BL-20260901-06,
  // `lsat-static/components/solve/SolveAssist.tsx`): H opens the guide and
  // then walks it forward, J and K move back and forward through what is
  // already revealed, R jumps to the final step once the question is graded.
  // Declared before the guide-less early return so the hook order never
  // changes between renders.
  //
  // Window-level and unguarded by a card scope, because exactly one question
  // — and so exactly one guide — is on screen at a time in every panel
  // (BL-20260901-08). `useShortcuts` skips text fields and open dialogs, so
  // the tutor's follow-up box keeps its letters.
  useShortcuts({
    h: () => {
      if (noGuide) return
      if (revealed === 0) void reveal()
      else goNext()
    },
    k: () => {
      if (guide && active < frontier) setActive((a) => a + 1)
    },
    j: () => {
      if (guide) setActive((a) => Math.max(0, a - 1))
    },
    r: () => {
      if (guide && graded && hasLockedVisible) void showFinal()
    },
  })

  if (noGuide) {
    return (
      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-400">
        No step-by-step guide for this question yet.
        {noGuide.hasTutor && onAskTutor && (
          <button
            type="button"
            onClick={onAskTutor}
            className="ml-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20"
          >
            Ask the AI tutor for a walkthrough
          </button>
        )}
      </div>
    )
  }

  return (
    <section aria-label="Solve assist" className="mt-4">
      <div className="flex flex-wrap items-center gap-3">
        {revealed === 0 && (
          <button
            type="button"
            onClick={() => void reveal()}
            disabled={loading}
            aria-expanded={false}
            className="inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-40"
          >
            {loading ? 'Loading…' : '💡 Hint'}
          </button>
        )}
        {graded && hasLockedVisible && (
          <button
            type="button"
            onClick={() => void showFinal()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-40"
          >
            Show final step
          </button>
        )}
        {guide && revealed > 0 && (
          <span className="text-[11px] text-slate-500">
            {guide.method} · step {Math.min(active + 1, guide.step_count)} of{' '}
            {guide.step_count}
          </span>
        )}
      </div>

      {error && (
        <p className="mt-2 text-sm text-red-300" role="alert">
          {error}
          <button
            type="button"
            onClick={() => void loadGuide(false)}
            className="ml-2 underline hover:text-red-200"
          >
            Retry
          </button>
        </p>
      )}

      {guide && currentStep && (
        <div
          role="region"
          aria-roledescription="carousel"
          aria-label="Solve guide steps"
          className="mt-3"
        >
          <div aria-live="polite">
            <StepSlide
              step={currentStep}
              index={active}
              total={guide.step_count}
            />
          </div>
          <div className="mt-2 flex items-center justify-between gap-3">
            <button
              type="button"
              aria-label="Previous step"
              onClick={() => setActive((a) => Math.max(0, a - 1))}
              disabled={active === 0}
              className="rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-xs font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white disabled:opacity-30"
            >
              ‹ Back
            </button>
            <div className="flex items-center gap-1.5" aria-hidden={false}>
              {guide.steps.map((s, i) =>
                i < revealed ? (
                  <button
                    key={i}
                    type="button"
                    aria-label={`Go to step ${i + 1}`}
                    aria-current={i === active ? 'step' : undefined}
                    onClick={() => setActive(i)}
                    className={
                      'h-2.5 w-2.5 rounded-full transition ' +
                      (i === active
                        ? 'bg-sky-400'
                        : 'bg-slate-600 hover:bg-slate-400')
                    }
                  />
                ) : (
                  <span
                    key={i}
                    aria-hidden="true"
                    className="h-2.5 w-2.5 rounded-full border border-slate-700"
                  />
                ),
              )}
            </div>
            <button
              type="button"
              onClick={goNext}
              disabled={!canGoNext || loading}
              className={
                'rounded-md px-2.5 py-1 text-xs font-semibold transition disabled:opacity-30 ' +
                (nextWillReveal
                  ? 'border border-sky-500/40 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20'
                  : 'border border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-500 hover:text-white')
              }
            >
              {nextWillReveal ? '💡 Next hint ›' : 'Next ›'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
