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
  type LsatDifficulty,
  type LsatQuestion,
} from '@/lib/api'
import { ErrorBanner, SkeletonQuestion } from '@/components/lsat/LabPrimitives'
import QuestionCard from '@/components/lsat/QuestionCard'
import { DIFFICULTIES, type AttemptHandler } from '@/components/lsat/labTabs'

export default function LrPanel({ onAttempt }: { onAttempt: AttemptHandler }) {
  const [difficulty, setDifficulty] = useState<LsatDifficulty | 'any'>('any')
  const [question, setQuestion] = useState<LsatQuestion | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const cardRef = useRef<HTMLDivElement | null>(null)
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
      })
      setQuestion(body.questions[0] ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [difficulty])

  useEffect(() => {
    void load()
  }, [load])

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
      />
      {loading && <SkeletonQuestion />}
      {!loading && error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && question && (
        <QuestionCard
          cardRef={cardRef}
          question={question}
          onResolved={(r, elapsed, hints) => onAttempt(r.correct, elapsed, hints)}
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
}: {
  difficulty: LsatDifficulty | 'any'
  onDifficulty: (d: LsatDifficulty | 'any') => void
  rightLabel: string
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <label
          htmlFor="lsat-diff"
          className="text-xs uppercase tracking-wider text-slate-500"
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
      <div className="text-xs uppercase tracking-wider text-slate-500">
        {rightLabel}
      </div>
    </div>
  )
}
