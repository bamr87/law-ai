'use client'

/**
 * Passage / game panel — shared by RC and LG. A passage (or game setup) on
 * the left, one of its linked questions on the right, with a numbered strip to
 * jump between them.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02. The
 * question column was a single stacked list until BL-20260901-08: with every
 * question on screen at once there was nothing for `N`/`P` to mean, so RC and
 * LG were the only sections you had to Tab through — while LR advanced from
 * the keyboard and the published static site advertised N/P for all three.
 * The reader half is mirrored by `lsat-static/components/PassagePanel.tsx`,
 * and this drill now pages the way `lsat-static/components/Drill.tsx` does.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchLsatPassage,
  fetchLsatPassages,
  fetchLsatQuestions,
  type LsatPassage,
  type LsatQuestion,
} from '@/lib/api'
import {
  ConceptChip,
  ErrorBanner,
  SkeletonGrid,
  SkeletonQuestion,
} from '@/components/lsat/LabPrimitives'
import QuestionCard, { type SavedAnswer } from '@/components/lsat/QuestionCard'
import type { AttemptHandler } from '@/components/lsat/labTabs'
import { setRemainingQuestions } from '@/lib/lsat/timerStore'

export default function PassagePanel({
  section,
  onAttempt,
  concept,
  onClearConcept,
}: {
  section: 'RC' | 'LG'
  onAttempt: AttemptHandler
  /**
   * Drill only the questions tagged with this concept (BL-20260905-01).
   *
   * Two thirds of the concepts the bank actually tags are RC- or LG-only, so a
   * `?concept=` entry point that only LR understood sent the library's "drill
   * this (21 questions)" link to a panel that answered "no questions are
   * tagged that" — worse than no link at all. The passage list narrows to the
   * sets that carry the tag and each set's stack narrows to the tagged
   * questions, so the tag → material → practice path completes here too.
   */
  concept?: string
  onClearConcept?: () => void
}) {
  const [passages, setPassages] = useState<LsatPassage[] | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [questions, setQuestions] = useState<LsatQuestion[]>([])
  const [activePassage, setActivePassage] = useState<LsatPassage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingPassages, setLoadingPassages] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  // One question at a time (BL-20260901-08). Stacking the whole set in a
  // column left RC/LG with no per-question `N`/`P` — Tab was the only route
  // between questions, while LR advanced from the keyboard and the published
  // static site advertised N/P for all three sections.
  const [activeIndex, setActiveIndex] = useState(0)
  // The answers the panel holds on the learner's behalf: the card is keyed on
  // the question, so anything it owns is destroyed on the way past. This is
  // what makes `P` show the answer you already gave instead of a blank card,
  // and it is the same trick `lsat-static/components/Drill.tsx` plays.
  const [answers, setAnswers] = useState<ReadonlyMap<string, SavedAnswer>>(
    () => new Map(),
  )
  const cardRef = useRef<HTMLDivElement | null>(null)
  // Bumped by navigation and only by navigation, so the focus effect can tell
  // "the learner moved" from "this stack just loaded" — the latter must not
  // steal focus out of the passage select they are still tabbing through.
  const [moves, setMoves] = useState(0)

  // Which sets carry the concept, when one is being drilled. `null` means "not
  // known yet" — the passage list stays unresolved rather than flashing the
  // whole section and then narrowing, which would fetch a set the learner
  // never asked for.
  const [taggedPassageIds, setTaggedPassageIds] =
    useState<ReadonlySet<string> | null>(null)

  useEffect(() => {
    if (!concept) {
      setTaggedPassageIds(null)
      return
    }
    let live = true
    void (async () => {
      try {
        // `section` + `concept` together: the bank endpoint already answers
        // this, so no passage has to be opened to find out whether it carries
        // the tag.
        const body = await fetchLsatQuestions({ section, concept, limit: 25 })
        if (!live) return
        setTaggedPassageIds(
          new Set(
            body.questions
              .map((q) => q.passage_id)
              .filter((id): id is string => Boolean(id)),
          ),
        )
      } catch (e) {
        if (!live) return
        setError(e instanceof Error ? e.message : 'Failed to load the concept')
        setTaggedPassageIds(new Set())
      }
    })()
    return () => {
      live = false
    }
  }, [concept, section])

  useEffect(() => {
    void (async () => {
      setLoadingPassages(true)
      setError(null)
      try {
        const body = await fetchLsatPassages(section)
        setPassages(body.passages)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passages')
      } finally {
        setLoadingPassages(false)
      }
    })()
  }, [section])

  // The sets on offer: every one in the section, or only those carrying the
  // concept. `null` while either half is still unknown, so the select and the
  // auto-open below wait for the real list instead of acting on a stale one.
  const shownPassages = useMemo(() => {
    if (passages === null) return null
    if (!concept) return passages
    if (taggedPassageIds === null) return null
    return passages.filter((p) => taggedPassageIds.has(p.id))
  }, [passages, concept, taggedPassageIds])

  // Open the first set on offer, and re-open when the concept filter takes the
  // current one away — a select showing a passage that is no longer in its own
  // option list is how the LR-only version of this deep link went wrong.
  useEffect(() => {
    if (!shownPassages || shownPassages.length === 0) return
    if (activeId && shownPassages.some((p) => p.id === activeId)) return
    setActiveId(shownPassages[0].id)
  }, [shownPassages, activeId])

  useEffect(() => {
    if (!activeId) return
    void (async () => {
      setLoadingDetail(true)
      setActiveIndex(0)
      setMoves(0)
      setAnswers(new Map())
      try {
        // Per-attempt shuffling (BL-20260606-01): RC and LG come through
        // this endpoint, so the request has to ask for it the way LrPanel
        // does — the card already echoes `question.remap` at grade time.
        const body = await fetchLsatPassage(activeId, { shuffle: true })
        setActivePassage(body.passage)
        setQuestions(body.questions)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passage')
      } finally {
        setLoadingDetail(false)
      }
    })()
  }, [activeId])

  // The stack actually being drilled: the set's questions, or only those
  // carrying the concept from the URL. Everything downstream — the strip, the
  // "question N of M" announcement, N/P, the pace on the clock — reads this,
  // so a filtered stack behaves exactly like a short one.
  const shownQuestions = useMemo(() => {
    if (!concept) return questions
    return questions.filter((q) => (q.concepts ?? []).includes(concept))
  }, [questions, concept])

  // The ungraded questions left in the open stack, published to the timer
  // store because the clock may be docked in a parallel-route slot and cannot
  // be reached with a prop (BL-20260829-01). Cleared on unmount: leaving the
  // stack must not leave a stale pace on the clock.
  useEffect(() => {
    const ungraded = shownQuestions.filter((q) => !answers.has(q.id)).length
    setRemainingQuestions(shownQuestions.length === 0 ? null : ungraded)
  }, [shownQuestions, answers])
  useEffect(() => () => setRemainingQuestions(null), [])

  // Read the index through a ref so `go` never has to be rebuilt: it is passed
  // into the card as `onNext`/`onPrev`, and a fresh identity every render
  // would rebind the card's handler on every keystroke.
  const indexRef = useRef(0)
  const lastRef = useRef(0)
  useEffect(() => {
    indexRef.current = activeIndex
    lastRef.current = shownQuestions.length - 1
  })
  const go = useCallback((to: number) => {
    const next = Math.max(0, Math.min(lastRef.current, to))
    if (next === indexRef.current) return
    setActiveIndex(next)
    setMoves((m) => m + 1)
  }, [])
  // Stable identities: these are the card's `onNext`/`onPrev`, and a fresh
  // closure every render would rebind its key handler on every keystroke.
  const nextQuestion = useCallback(() => go(indexRef.current + 1), [go])
  const prevQuestion = useCallback(() => go(indexRef.current - 1), [go])

  // Land the reader on the new question. Without this, `N` left focus on
  // <body> — outside the element every drill shortcut is bound to, so the
  // *next* keystroke did nothing (the same stall LR fixed at its own card).
  useEffect(() => {
    if (moves === 0) return
    cardRef.current?.focus()
  }, [moves])

  const headline = section === 'RC' ? 'Reading Comprehension' : 'Logic Games'
  const last = shownQuestions.length - 1
  const active =
    shownQuestions.length > 0
      ? shownQuestions[Math.min(activeIndex, last)]
      : null

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-slate-500">
          Section: {headline}
        </div>
        {concept && <ConceptChip concept={concept} onClear={onClearConcept} />}
        {shownPassages && shownPassages.length > 0 && (
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
              {shownPassages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {(loadingPassages || (Boolean(concept) && !shownPassages)) && !error && (
        <SkeletonGrid />
      )}
      {error && <ErrorBanner message={error} />}
      {!loadingPassages && !error && shownPassages?.length === 0 && (
        // A tag with nothing behind it in this section has to say so, and say
        // it about the tag rather than about the section — the library
        // advertises a question count over the whole bank, so "21 questions"
        // can still mean "none in Reading Comprehension" (BL-20260905-01).
        <p className="text-sm text-slate-400">
          {concept ? (
            <>
              {`No ${headline} questions are tagged ${concept} yet.`}
              {onClearConcept && (
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
            </>
          ) : (
            `No ${headline.toLowerCase()} passages have been authored yet.`
          )}
        </p>
      )}

      {activePassage && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <PassageReader passage={activePassage} />
          <div className="space-y-4">
            {loadingDetail && <SkeletonQuestion />}
            {!loadingDetail && active && (
              <>
                <QuestionStrip
                  questions={shownQuestions}
                  activeIndex={Math.min(activeIndex, last)}
                  answered={answers}
                  onPick={go}
                />
                {/* Position, announced. Paging a stack one question at a time
                 * is only navigable if you are told where you landed. */}
                <p className="sr-only" role="status" aria-live="polite">
                  Question {Math.min(activeIndex, last) + 1} of{' '}
                  {shownQuestions.length}.
                </p>
                <QuestionCard
                  key={active.id}
                  cardRef={cardRef}
                  question={active}
                  saved={answers.get(active.id) ?? null}
                  onResolved={(r, elapsed, hints, choice) => {
                    if (choice) {
                      setAnswers((prev) =>
                        new Map(prev).set(active.id, {
                          choice,
                          result: r,
                          elapsedSeconds: elapsed,
                        }),
                      )
                    }
                    onAttempt(r.correct, elapsed, hints)
                  }}
                  browsable={shownQuestions.length > 1}
                  onNext={activeIndex < last ? nextQuestion : undefined}
                  onPrev={activeIndex > 0 ? prevQuestion : undefined}
                  compact
                />
              </>
            )}
            {!loadingDetail && shownQuestions.length === 0 && (
              <p className="text-sm text-slate-400">
                {concept
                  ? `No question in this ${section === 'LG' ? 'game' : 'passage'} is tagged ${concept}.`
                  : `No questions linked to this ${section === 'LG' ? 'game' : 'passage'}.`}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

/**
 * The numbered jump strip. Paging one question at a time is only navigable if
 * you can see how many there are, which ones you have answered, and get to any
 * of them without walking the whole stack.
 */
function QuestionStrip({
  questions,
  activeIndex,
  answered,
  onPick,
}: {
  questions: LsatQuestion[]
  activeIndex: number
  answered: ReadonlyMap<string, SavedAnswer>
  onPick: (index: number) => void
}) {
  if (questions.length < 2) return null
  return (
    <div
      role="group"
      aria-label="Questions in this set"
      className="flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/50 px-3 py-2 backdrop-blur"
    >
      <span className="mr-1 text-[11px] uppercase tracking-wider text-slate-500">
        Question {activeIndex + 1} / {questions.length}
      </span>
      {questions.map((q, i) => {
        const saved = answered.get(q.id)
        const active = i === activeIndex
        let cls =
          'tap-target inline-flex h-7 min-w-[1.75rem] items-center justify-center rounded-md border px-2 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 '
        if (active) cls += 'border-blue-500/60 bg-blue-500/20 text-blue-100'
        else if (saved)
          cls += saved.result.correct
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
            : 'border-red-500/40 bg-red-500/10 text-red-200'
        else
          cls +=
            'border-slate-700 bg-slate-950/40 text-slate-300 hover:border-slate-500 hover:text-white'
        return (
          <button
            key={q.id}
            type="button"
            onClick={() => onPick(i)}
            aria-current={active ? 'true' : undefined}
            // The state is in the colour too, and colour alone is not a
            // status: spell it out for anyone who cannot see the swatch.
            aria-label={
              `Question ${i + 1}` +
              (saved
                ? saved.result.correct
                  ? ', answered correctly'
                  : ', answered incorrectly'
                : ', unanswered')
            }
            className={cls}
          >
            {i + 1}
          </button>
        )
      })}
    </div>
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
