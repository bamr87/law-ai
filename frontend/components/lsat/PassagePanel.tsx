'use client'

/**
 * Passage / game panel — shared by RC and LG. A passage (or game setup) on
 * the left, its linked questions stacked on the right.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02. Its
 * counterpart is `lsat-static/components/PassagePanel.tsx` (the reader half;
 * the static drill pages questions one at a time instead of stacking them).
 */

import { useEffect, useState } from 'react'

import {
  fetchLsatPassage,
  fetchLsatPassages,
  type LsatPassage,
  type LsatQuestion,
} from '@/lib/api'
import {
  ErrorBanner,
  SkeletonGrid,
  SkeletonQuestion,
} from '@/components/lsat/LabPrimitives'
import QuestionCard from '@/components/lsat/QuestionCard'
import type { AttemptHandler } from '@/components/lsat/labTabs'

export default function PassagePanel({
  section,
  onAttempt,
}: {
  section: 'RC' | 'LG'
  onAttempt: AttemptHandler
}) {
  const [passages, setPassages] = useState<LsatPassage[] | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [questions, setQuestions] = useState<LsatQuestion[]>([])
  const [activePassage, setActivePassage] = useState<LsatPassage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingPassages, setLoadingPassages] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [elapsedQuestionId, setElapsedQuestionId] = useState<string | null>(
    null,
  )

  useEffect(() => {
    void (async () => {
      setLoadingPassages(true)
      setError(null)
      try {
        const body = await fetchLsatPassages(section)
        setPassages(body.passages)
        if (body.passages.length > 0 && !activeId) {
          setActiveId(body.passages[0].id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passages')
      } finally {
        setLoadingPassages(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section])

  useEffect(() => {
    if (!activeId) return
    void (async () => {
      setLoadingDetail(true)
      setElapsedQuestionId(null)
      try {
        const body = await fetchLsatPassage(activeId)
        setActivePassage(body.passage)
        setQuestions(body.questions)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passage')
      } finally {
        setLoadingDetail(false)
      }
    })()
  }, [activeId])

  const headline = section === 'RC' ? 'Reading Comprehension' : 'Logic Games'

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-slate-500">
          Section: {headline}
        </div>
        {passages && passages.length > 0 && (
          <div className="flex items-center gap-2">
            <label
              htmlFor="passage-select"
              className="text-xs uppercase tracking-wider text-slate-500"
            >
              {section === 'LG' ? 'Game' : 'Passage'}
            </label>
            <select
              id="passage-select"
              value={activeId ?? ''}
              onChange={(e) => setActiveId(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus-ring"
            >
              {passages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {loadingPassages && <SkeletonGrid />}
      {error && <ErrorBanner message={error} />}
      {!loadingPassages && passages && passages.length === 0 && (
        <p className="text-sm text-slate-400">
          No {headline.toLowerCase()} passages have been authored yet.
        </p>
      )}

      {activePassage && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <PassageReader passage={activePassage} />
          <div className="space-y-4">
            {loadingDetail && <SkeletonQuestion />}
            {!loadingDetail &&
              questions.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  onResolved={(r, elapsed, hints) => onAttempt(r.correct, elapsed, hints)}
                  compact
                  elapsedEnabled={elapsedQuestionId === q.id}
                  onActivate={() => setElapsedQuestionId(q.id)}
                />
              ))}
            {!loadingDetail && questions.length === 0 && (
              <p className="text-sm text-slate-400">
                No questions linked to this {section === 'LG' ? 'game' : 'passage'}.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

export function PassageReader({ passage }: { passage: LsatPassage }) {
  // Spec 047 FR-9: a comparative set carries two texts, and every question in
  // the set names one of them — so both need visible headings, not one blob.
  const comparative = Boolean(passage.passage_b)
  return (
    <article className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-amber-400">
        {passage.section === 'LG'
          ? 'Game setup'
          : comparative
            ? 'Comparative passages'
            : 'Reading passage'}
      </div>
      <h3 className="mt-1 text-lg font-semibold text-slate-100">
        {passage.title}
      </h3>
      {passage.summary && (
        <p className="mt-1 text-xs italic text-slate-500">{passage.summary}</p>
      )}
      {passage.passage && comparative && (
        <h4 className="mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
          {passage.title_a ?? 'Passage A'}
        </h4>
      )}
      {passage.passage && (
        <p
          className={
            (comparative ? 'mt-2' : 'mt-4') +
            ' whitespace-pre-line text-sm leading-relaxed text-slate-200'
          }
        >
          {passage.passage}
        </p>
      )}
      {passage.passage_b && (
        <>
          <h4 className="mt-5 border-t border-slate-800 pt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
            {passage.title_b ?? 'Passage B'}
          </h4>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-200">
            {passage.passage_b}
          </p>
        </>
      )}
      {passage.setup && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {passage.setup}
        </p>
      )}
      {passage.rules.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            Rules
          </div>
          <ul className="mt-2 list-inside list-decimal space-y-1 text-sm text-slate-200">
            {passage.rules.map((r) => (
              <li key={r}>{r.replace(/^\d+\.\s*/, '')}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}
