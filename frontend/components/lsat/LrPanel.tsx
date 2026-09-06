'use client'

/**
 * Logical Reasoning panel — one isolated question at a time, drawn from the
 * bank at the chosen difficulty.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — the static export drills every section through one
 * `Drill.tsx` that pages a fixed list; this panel draws from `/api/lsat/questions`
 * with a difficulty filter, which the build-time bundle has no server for.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  fetchLsatQuestions,
  fetchLsatSections,
  type LsatDifficulty,
  type LsatQuestion,
} from '@/lib/api'
import { setRemainingQuestions } from '@/lib/lsat/timerStore'
import { LSAT_SECTION_QUESTIONS } from '@/lib/lsatTimer'
import {
  ConceptChip,
  ErrorBanner,
  SkeletonQuestion,
} from '@/components/lsat/LabPrimitives'
import QuestionCard from '@/components/lsat/QuestionCard'
import { DIFFICULTIES, type AttemptHandler } from '@/components/lsat/labTabs'

export default function LrPanel({
  onAttempt,
  concept,
  onClearConcept,
}: {
  onAttempt: AttemptHandler
  /**
   * Draw only from questions tagged with this concept (BL-20260905-01). Set by
   * the lab from `?concept=<id>`, which is how the library's catalog links a
   * tag straight through to practice.
   */
  concept?: string
  onClearConcept?: () => void
}) {
  const [difficulty, setDifficulty] = useState<LsatDifficulty | 'any'>('any')
  const [question, setQuestion] = useState<LsatQuestion | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const cardRef = useRef<HTMLDivElement | null>(null)
  // Pace inputs. LR has no fixed stack — it deals one question at a time out
  // of the bank — so the drill borrows the real section's length: 25 items,
  // minus what this session has already graded. It used to publish the whole
  // bank, which quoted an 8-second-per-question pace off a 200-item bank
  // (BL-20260905-32). The bank size still caps it: a 6-question bank cannot
  // fill a section, and pacing for 25 there would be the same lie inverted.
  const [bankSize, setBankSize] = useState<number | null>(null)
  const [graded, setGraded] = useState(0)
  // Set only by "next", so changing the difficulty — which reloads through the
  // same path while the user is still in the select — never yanks focus.
  const advanced = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const body = await fetchLsatQuestions({
        limit: 1,
        section: 'LR',
        difficulty: difficulty === 'any' ? undefined : difficulty,
        concept,
        // Per-attempt shuffling (BL-20260606-01): the key must not sit in the
        // same place every time a question comes round again.
        shuffle: true,
      })
      setQuestion(body.questions[0] ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [difficulty, concept])

  useEffect(() => {
    void load()
  }, [load])

  // The bank size the Overview panel shows as "Items in bank", fetched once —
  // here only as the cap on a short bank. A failure is silent: no pace readout
  // is a smaller loss than an error banner over a working drill.
  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchLsatSections()
        const lr = body.sections.find((s) => s.code === 'LR')
        if (live && lr) setBankSize(lr.question_count)
      } catch {
        /* pace readout stays hidden */
      }
    })()
    return () => {
      live = false
    }
  }, [])

  // Publish the count to the timer store, and clear it on the way out so the
  // clock stops quoting a pace for a section the student has left.
  useEffect(() => {
    if (bankSize === null) {
      setRemainingQuestions(null)
      return
    }
    const section = Math.min(bankSize, LSAT_SECTION_QUESTIONS)
    // Past a full section the readout blanks rather than going negative: the
    // section the clock was timing is over.
    setRemainingQuestions(Math.max(0, section - graded))
  }, [bankSize, graded])
  useEffect(() => () => setRemainingQuestions(null), [])

  const loadNext = useCallback(() => {
    advanced.current = true
    void load()
  }, [load])

  // Drawing the next question unmounts the card (the panel shows a skeleton
  // while it fetches), which dropped focus to <body> — outside the element the
  // drill's key handler is bound to, so the *following* keystroke did nothing
  // and the run stalled until someone reached for the mouse.
  useEffect(() => {
    if (!advanced.current || loading || !question) return
    advanced.current = false
    cardRef.current?.focus()
  }, [loading, question])

  return (
    <section className="space-y-4">
      <Toolbar
        difficulty={difficulty}
        onDifficulty={setDifficulty}
        rightLabel={`Section: Logical Reasoning`}
        concept={concept}
        onClearConcept={onClearConcept}
      />
      {loading && <SkeletonQuestion />}
      {!loading && error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && !question && (
        // An empty pool has to say so. Without this the panel rendered nothing
        // at all, and a concept with no LR questions looked like a broken link
        // rather than a gap in the bank.
        <p className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-400">
          {concept
            ? `No Logical Reasoning questions are tagged ${concept} yet.`
            : 'No Logical Reasoning questions match this filter yet.'}
          {concept && onClearConcept && (
            <>
              {' '}
              <button
                type="button"
                onClick={onClearConcept}
                className="underline underline-offset-2 hover:text-slate-200"
              >
                Drill the whole section instead
              </button>
              .
            </>
          )}
        </p>
      )}
      {!loading && !error && question && (
        <QuestionCard
          cardRef={cardRef}
          question={question}
          onResolved={(r, elapsed, hints) => {
            setGraded((n) => n + 1)
            onAttempt(r.correct, elapsed, hints)
          }}
          onNext={loadNext}
        />
      )}
    </section>
  )
}

function Toolbar({
  difficulty,
  onDifficulty,
  rightLabel,
  concept,
  onClearConcept,
}: {
  difficulty: LsatDifficulty | 'any'
  onDifficulty: (d: LsatDifficulty | 'any') => void
  rightLabel: string
  concept?: string
  onClearConcept?: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <label
          htmlFor="lsat-diff"
          className="text-xs uppercase tracking-wider text-slate-400"
        >
          Difficulty
        </label>
        <select
          id="lsat-diff"
          value={difficulty}
          onChange={(e) =>
            onDifficulty(e.target.value as LsatDifficulty | 'any')
          }
          className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus-ring"
        >
          {DIFFICULTIES.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>
      </div>
      {concept && (
        // The filter is visible and reversible. A deep link that silently
        // narrows the bank and gives no way back is a trap, not a shortcut.
        // Shared with the passage panels, which take the same deep link.
        <ConceptChip concept={concept} onClear={onClearConcept} />
      )}
      <div className="text-xs uppercase tracking-wider text-slate-400">
        {rightLabel}
      </div>
    </div>
  )
}
