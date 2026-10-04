'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Question, SectionCode } from '@/lib/types'
import { passageById, questionsFor, sectionMeta } from '@/lib/data'
import QuestionCard from './QuestionCard'
import PassagePanel from './PassagePanel'
import SectionTimer from './SectionTimer'
import { useShortcuts } from '@/lib/keyboard'
import { useMeasuredCssVar } from '@/lib/useMeasuredCssVar'
import {
  beginSection,
  recordAnswer,
  setRemainingQuestions,
} from '@/lib/lsat/timerStore'
import {
  type DrillPosition,
  readDrillPosition,
  writeDrillPosition,
} from '@/lib/deviceState'

/** What the drill remembers about a question you have already answered. */
interface Answer {
  choice: string
  seconds: number
}

/**
 * A saved position brought back into the shape the drill works in.
 *
 * Answers are dropped unless the question is still in the bank: `content.json`
 * is regenerated, so a record written weeks ago can name questions that no
 * longer exist, and carrying them would inflate `answers.size` — which is the
 * pace denominator the timer publishes (BL-20260829-01).
 */
function restore(
  saved: DrillPosition | null,
  questions: Question[],
): { i: number; answers: Map<string, Answer> } {
  if (!saved) return { i: 0, answers: new Map() }
  const ids = new Set(questions.map((q) => q.id))
  return {
    // Clamp to the bank as it is now: an index past the end would render the
    // last question while the progress readout quoted a number that is not
    // there.
    i: Math.min(saved.i, Math.max(0, questions.length - 1)),
    answers: new Map(
      Object.entries(saved.answers).filter(([qid]) => ids.has(qid)),
    ),
  }
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
  // Where this section was left, read once on mount (BL-20260916-01).
  //
  // `app/page.tsx` keys the view wrapper on `view`, so changing destination
  // unmounts this component outright — checking Stats mid-section threw the
  // reader's place away while the attempts (`lib/progress.ts`) and the clock
  // (`lib/lsat/timerStore.ts`) both survived, because neither lives in the
  // component tree. Of the site's three tiers of state the drill was on the
  // only one a remount can erase.
  //
  // Read during render rather than from an effect, which is the opposite of
  // the rule `app/page.tsx` follows for the header pin — and the difference is
  // the prerender. `Page` is rendered by the static export, so a first paint
  // that disagreed with storage would be a hydration mismatch; `Drill` is not,
  // because the page opens on 'overview' and no section is mounted until the
  // reader clicks one, long after hydration. Reading here therefore costs
  // nothing and buys two things: no flash of question 1 before the effect
  // lands, and no setState-in-an-effect cascade.
  const [restored] = useState(() => restore(readDrillPosition(section), questions))
  const [i, setI] = useState(restored.i)
  // The answer *and* the time, not just the time: the card is keyed on the
  // question, so whatever the drill does not hold here is destroyed the moment
  // you move off a question and rebuilt blank when you come back.
  const [answers, setAnswers] = useState<Map<string, Answer>>(restored.answers)
  const cardRef = useRef<HTMLElement | null>(null)
  // Second rung of the sticky stack: the passage column hangs off
  // `--drill-head-h`, so the token follows this element rather than a constant
  // that has to be re-measured by hand (BL-20260831-20).
  const headRef = useRef<HTMLDivElement | null>(null)
  useMeasuredCssVar(headRef, '--drill-head-h', { onlyWhen: '(min-width: 820px)' })
  // Bumped by every navigation, and only by navigation, so the focus effect
  // below can tell "the user moved" from "this section just mounted" — the
  // latter must not steal focus out of the nav the user is still tabbing.
  const [moves, setMoves] = useState(0)

  // Two resets on a section change, with two different owners — which is the
  // distinction that was missing, and the whole of BL-20260916-03.
  //
  // The clock lives in a module store, shared with the platform and deliberately
  // outliving this component (BL-20260830-04). The index and answers below live
  // in this component. A ref can only speak for the second: `app/page.tsx` keys
  // the view wrapper on `view`, so switching section unmounts the drill and
  // mounts a fresh one whose `useRef(section)` initialises to the *new* section
  // — the comparison is then true on the first run, the early return always
  // taken, and `resetSection()` was unreachable. Meanwhile the store, by design,
  // kept LR's counters and handed them to RC.
  //
  // For the component's own state the ref is still exactly right, and for the
  // same reason: it is only ever consulted by the instance that owns that state,
  // and a fresh instance starts fresh anyway. So the ref stays where it works,
  // and the clock is claimed from the store, which is the one participant in a
  // section switch that is not remounted and can therefore still tell a change
  // of section from a first mount.
  const lastSection = useRef(section)
  useEffect(() => {
    beginSection(section)
    if (lastSection.current === section) return
    lastSection.current = section
    setI(0)
    setAnswers(new Map())
    setMoves(0)
  }, [section])

  // Write the position back on every change, so the next mount can read it.
  //
  // `moves` is deliberately untouched by any of this. It is what tells the
  // focus effect above that *the user* moved, and arriving on a restored
  // position is not a move — bumping it would land focus on the card while the
  // reader was still on the nav button they clicked, which is the regression
  // `Drill.test.tsx` pins for mounting.
  useEffect(() => {
    writeDrillPosition(section, { i, answers: Object.fromEntries(answers) })
  }, [section, i, answers])

  // Read through a ref rather than a `setI` updater: the move counter has to
  // move with the index, and a state updater has to stay pure. Seeded from the
  // restored index, not 0, so it mirrors `i` from the first render rather than
  // from the first effect.
  const iRef = useRef(restored.i)
  useEffect(() => {
    iRef.current = i
  })
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

  // The pace denominator, published to the shared timer store rather than
  // passed down: the platform's clock docks into panels the drill cannot reach
  // with a prop, and the two products render the same readout from the same
  // number (BL-20260829-01).
  useEffect(() => {
    setRemainingQuestions(
      questions.length === 0 ? null : questions.length - answers.size,
    )
  }, [questions, answers])
  useEffect(() => () => setRemainingQuestions(null), [])

  if (questions.length === 0) {
    return <p className="empty">No questions in this section yet.</p>
  }
  const passage = passageById(q.passage_id)
  const saved = answers.get(q.id)

  return (
    <section aria-label={`${meta?.name ?? section} drill`}>
      <div className="drill-head" ref={headRef}>
        <div>
          <h2>{meta?.name ?? section}</h2>
          {meta?.timing && <p className="drill-timing">{meta.timing}</p>}
        </div>
        <SectionTimer />
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
              // Pace counters live in the timer store, and only a *first*
              // answer counts: paging back over a question you already
              // answered must not bill the section for it twice.
              if (!answers.has(q.id)) recordAnswer(elapsedSeconds)
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
