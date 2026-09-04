'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { SectionCode } from '@/lib/types'
import { passageById, questionsFor, sectionMeta } from '@/lib/data'
import QuestionCard from './QuestionCard'
import PassagePanel from './PassagePanel'
import SectionTimer from './SectionTimer'
import { useShortcuts } from '@/lib/keyboard'

/** What the drill remembers about a question you have already answered. */
interface Answer {
  choice: string
  seconds: number
}

/** Question-by-question drill for one section, with prev/next navigation. */
export default function Drill({
  section,
  onAnnounce,
}: {
  section: SectionCode
  onAnnounce?: (msg: string) => void
}) {
  const questions = useMemo(() => questionsFor(section), [section])
  const meta = sectionMeta(section)
  const [i, setI] = useState(0)
  // The answer *and* the time, not just the time: the card is keyed on the
  // question, so whatever the drill does not hold here is destroyed the moment
  // you move off a question and rebuilt blank when you come back.
  const [answers, setAnswers] = useState<Map<string, Answer>>(() => new Map())
  const cardRef = useRef<HTMLElement | null>(null)
  // Bumped by every navigation, and only by navigation, so the focus effect
  // below can tell "the user moved" from "this section just mounted" — the
  // latter must not steal focus out of the nav the user is still tabbing.
  const [moves, setMoves] = useState(0)

  useEffect(() => {
    setI(0)
    setAnswers(new Map())
    setMoves(0)
  }, [section])

  // Read through a ref rather than a `setI` updater: the move counter has to
  // move with the index, and a state updater has to stay pure.
  const iRef = useRef(0)
  iRef.current = i
  const go = useCallback((next: (current: number) => number) => {
    const to = next(iRef.current)
    if (to === iRef.current) return
    setI(to)
    setMoves((m) => m + 1)
  }, [])

  const q = questions[Math.min(i, questions.length - 1)]
  const answered = q ? answers.has(q.id) : false

  // Land the reader on the new question. Without this, `N` left focus on
  // <body>: no focus ring for a sighted keyboard user, no position for a
  // screen reader, and a Tab that restarts at the top of the document.
  useEffect(() => {
    if (moves === 0) return
    cardRef.current?.focus()
    onAnnounce?.(`Question ${i + 1} of ${questions.length}.`)
    // `i` is deliberately not a dependency: `moves` is what says a move
    // happened, and reading `i` at that render is what makes the count right.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moves])

  // Question-to-question movement. `Enter` advances only once the current
  // question has been checked — before that it belongs to QuestionCard, which
  // uses it to submit. The two guards are mutually exclusive, so both can
  // listen for the same key without racing.
  useShortcuts({
    n: () => go((n) => Math.min(questions.length - 1, n + 1)),
    p: () => go((n) => Math.max(0, n - 1)),
    Enter: () => {
      if (answered) go((n) => Math.min(questions.length - 1, n + 1))
    },
  })

  if (questions.length === 0) {
    return <p className="empty">No questions in this section yet.</p>
  }
  const passage = passageById(q.passage_id)
  const answeredCount = answers.size
  const answeredSeconds = Array.from(answers.values()).reduce(
    (sum, a) => sum + a.seconds,
    0,
  )
  const saved = answers.get(q.id)

  return (
    <section aria-label={`${meta?.name ?? section} drill`}>
      <div className="drill-head">
        <div>
          <h2>{meta?.name ?? section}</h2>
          {meta?.timing && <p className="drill-timing">{meta.timing}</p>}
        </div>
        <SectionTimer
          key={section}
          remainingQuestions={questions.length - answeredCount}
          answeredCount={answeredCount}
          answeredSeconds={answeredSeconds}
        />
      </div>

      <div className="drill-grid">
        {passage && <PassagePanel passage={passage} />}
        <div className="drill-main">
          <QuestionCard
            key={q.id}
            cardRef={cardRef}
            question={q}
            index={i}
            total={questions.length}
            savedChoice={saved?.choice ?? null}
            savedSeconds={saved?.seconds ?? 0}
            onAnnounce={onAnnounce}
            onAnswered={(choice, elapsedSeconds) => {
              setAnswers((prev) => {
                if (prev.has(q.id)) return prev
                const next = new Map(prev)
                next.set(q.id, { choice, seconds: elapsedSeconds })
                return next
              })
            }}
          />

          <nav className="drill-nav" aria-label="Question navigation">
            <button
              type="button"
              className="btn"
              aria-keyshortcuts="P"
              onClick={() => go((n) => Math.max(0, n - 1))}
              disabled={i === 0}
            >
              ← Previous
            </button>
            <span className="drill-progress" aria-hidden="true">
              {i + 1} / {questions.length}
            </span>
            <button
              type="button"
              className="btn"
              aria-keyshortcuts="N"
              onClick={() => go((n) => Math.min(questions.length - 1, n + 1))}
              disabled={i >= questions.length - 1}
            >
              Next →
            </button>
          </nav>
        </div>
      </div>
    </section>
  )
}
