'use client'

import { useEffect, useMemo, useState } from 'react'
import type { SectionCode } from '@/lib/types'
import { passageById, questionsFor, sectionMeta } from '@/lib/data'
import QuestionCard from './QuestionCard'
import PassagePanel from './PassagePanel'
import SectionTimer from './SectionTimer'

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
  const [answers, setAnswers] = useState<Map<string, number>>(() => new Map())

  useEffect(() => {
    setI(0)
    setAnswers(new Map())
  }, [section])

  if (questions.length === 0) {
    return <p className="empty">No questions in this section yet.</p>
  }

  const q = questions[Math.min(i, questions.length - 1)]
  const passage = passageById(q.passage_id)
  const answeredCount = answers.size
  const answeredSeconds = Array.from(answers.values()).reduce((sum, n) => sum + n, 0)

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
            question={q}
            index={i}
            total={questions.length}
            onAnnounce={onAnnounce}
            onAnswered={(elapsedSeconds) => {
              setAnswers((prev) => {
                if (prev.has(q.id)) return prev
                const next = new Map(prev)
                next.set(q.id, elapsedSeconds)
                return next
              })
            }}
          />

          <nav className="drill-nav" aria-label="Question navigation">
            <button
              type="button"
              className="btn"
              onClick={() => setI((n) => Math.max(0, n - 1))}
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
              onClick={() => setI((n) => Math.min(questions.length - 1, n + 1))}
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
