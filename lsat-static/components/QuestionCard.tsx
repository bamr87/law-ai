'use client'

import ConceptRefs from './solve/ConceptRefs'
import SolveAssist from './solve/SolveAssist'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Question } from '@/lib/types'
import { recordAttempt } from '@/lib/progress'
import { useShortcuts } from '@/lib/keyboard'
import { nextRovingIndex } from '@/lib/rovingFocus'
import { permuteQuestion, toCanonical, toDisplay } from '@/lib/shuffle'
import { QuestionElapsed } from './QuestionElapsed'

interface Props {
  question: Question
  index: number
  total: number
  /**
   * The choice this question was already answered with, when the drill is
   * paging back over ground it has covered. Non-null mounts the card in its
   * checked state: `P` has to show the answer you gave and the key you were
   * shown, or moving back through a section is a way to lose your work rather
   * than a way to review it.
   */
  savedChoice?: string | null
  /** Seconds already spent on a restored question, so the clock is honest. */
  savedSeconds?: number
  /** The drill moves focus here on every question change. */
  cardRef?: React.Ref<HTMLElement>
  onAnnounce?: (msg: string) => void
  onAnswered?: (choice: string, elapsedSeconds: number) => void
}

/**
 * A single LSAT question with an accessible answer-choice radiogroup:
 * roving tabindex, Arrow-key selection-follows-focus, Space selects, Enter on
 * the selected choice submits. After submitting, the key + explanation are
 * revealed and the attempt is recorded to localStorage.
 *
 * The arrow/Home/End half of that contract is `nextRovingIndex` — the same
 * pure function the platform's `useRovingTabIndex` consumes, mirrored into
 * `lib/rovingFocus.ts` by `make ui-sync` and drift-gated by ux_audit R12 — so
 * the two products cannot disagree about what an arrow key means
 * (BL-20260831-08).
 */
export default function QuestionCard({
  question,
  index,
  total,
  savedChoice = null,
  savedSeconds = 0,
  cardRef,
  onAnnounce,
  onAnswered,
}: Props) {
  // Per-attempt shuffling (BL-20260606-01): the board this attempt shows, with
  // the key and the explanation moved to match. Drawn once per question per
  // session, so paging back reviews the board you answered.
  const shown = useMemo(() => permuteQuestion(question), [question])
  // A saved answer is stored in the bank's own labels; bring it into the order
  // on screen before restoring the selection.
  const savedDisplay = savedChoice ? toDisplay(savedChoice, shown.order) : null
  const [selected, setSelected] = useState<string | null>(savedDisplay)
  const [submitted, setSubmitted] = useState(savedChoice !== null)
  const optionRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const elapsedRef = useRef(savedSeconds)

  // Rehydrate when the question changes. The drill keys this component on the
  // question id so the initial state above already covers its own navigation;
  // this is what keeps the card correct if it is ever rendered unkeyed. Both
  // paths read the same saved answer, so it is idempotent.
  useEffect(() => {
    setSelected(savedDisplay)
    setSubmitted(savedChoice !== null)
  }, [question.id, savedChoice, savedDisplay])

  const labels = useMemo(() => shown.choices.map((c) => c.label), [shown.choices])

  function focusLabel(label: string) {
    setSelected(label)
    optionRefs.current[label]?.focus()
  }

  function submit() {
    if (submitted || !selected) return
    // Grade and record in the bank's labels — progress that meant "the third
    // choice on that screen" would be unreadable a session later.
    const canonical = toCanonical(selected, shown.order)
    const correct = canonical === question.correct
    setSubmitted(true)
    onAnswered?.(canonical, elapsedRef.current)
    recordAttempt({
      qid: question.id,
      section: question.section,
      choice: canonical,
      correct,
      // `submit` runs from a click or a keystroke, never during render, so the
      // clock read here is not a purity violation the way the rule assumes.
      // eslint-disable-next-line react-hooks/purity
      ts: Date.now(),
    })
    onAnnounce?.(correct ? 'Correct.' : `Incorrect. The correct answer is ${shown.correct}.`)
  }

  // Letter keys pick a choice from anywhere on the page — you should not have
  // to tab into the radiogroup from the passage to answer.
  //
  // The map is built from state rather than guarded inside the handlers,
  // because *registering* a key is what claims it: `useShortcuts` calls
  // `preventDefault()` before dispatching, and a later listener skips an event
  // that is already claimed. A permanently-bound `Enter` whose handler merely
  // no-opped after submitting therefore swallowed the keystroke and starved
  // Drill's Enter-to-advance. Bind only what can act.
  useShortcuts(
    submitted
      ? {}
      : {
          ...Object.fromEntries(
            labels.map((label) => [label.toLowerCase(), () => focusLabel(label)]),
          ),
          ...(selected ? { Enter: () => submit() } : {}),
        },
  )

  function onKeyDown(e: React.KeyboardEvent, label: string) {
    if (submitted) return
    // Movement: both axes, wrapping, Home/End, and never a modified chord.
    const next = nextRovingIndex(
      e,
      labels.indexOf(selected ?? label),
      labels.length,
      { orientation: 'both' },
    )
    if (next !== null) {
      e.preventDefault()
      focusLabel(labels[next])
      return
    }
    switch (e.key) {
      case ' ':
        e.preventDefault()
        setSelected(label)
        break
      case 'Enter':
        e.preventDefault()
        if (selected === label) submit()
        else setSelected(label)
        break
    }
  }

  return (
    <article
      ref={cardRef}
      // Programmatic focus target only — the drill moves focus here on every
      // question change so `N`/`P` land the user on the new stem instead of
      // dropping focus to <body>, where there is no ring to see and Tab
      // restarts from the top of the document.
      tabIndex={-1}
      className="qcard"
      aria-label={`Question ${index + 1} of ${total}`}
    >
      <div className="qcard-meta">
        <span className="pill">{question.section}</span>
        <span className="pill pill-muted">{question.type}</span>
        <span className="pill pill-muted">{question.difficulty}</span>
        <span className="qcard-count">
          {index + 1} / {total}
        </span>
        <QuestionElapsed
          key={question.id}
          startAt={savedSeconds}
          frozen={submitted}
          onTick={(s) => {
            elapsedRef.current = s
          }}
        />
      </div>

      <p className="qcard-stem">{question.stem}</p>

      <div
        role="radiogroup"
        aria-label="Answer choices"
        aria-keyshortcuts="A B C D E"
        className="choices"
      >
        {shown.choices.map((c) => {
          const isSelected = selected === c.label
          const isKey = submitted && c.label === shown.correct
          const isWrongPick = submitted && isSelected && c.label !== shown.correct
          const tabIndex = (selected ? isSelected : c.label === labels[0]) ? 0 : -1
          return (
            <button
              key={c.label}
              type="button"
              ref={(el) => {
                optionRefs.current[c.label] = el
              }}
              role="radio"
              aria-checked={isSelected}
              tabIndex={tabIndex}
              // `aria-disabled` rather than `disabled`: a disabled button is
              // removed from the focus order, so checking an answer while the
              // chosen choice had focus threw focus to <body> — no ring, no
              // screen-reader position, and Tab restarting at the skip link.
              // The graded choices stay reachable and readable; every handler
              // below already no-ops once submitted.
              aria-disabled={submitted}
              onClick={() => !submitted && setSelected(c.label)}
              onKeyDown={(e) => onKeyDown(e, c.label)}
              className={
                'choice' +
                (isSelected ? ' choice-selected' : '') +
                (isKey ? ' choice-correct' : '') +
                (isWrongPick ? ' choice-wrong' : '')
              }
            >
              <span className="choice-label" aria-hidden="true">
                {c.label}
              </span>
              <span className="choice-text">{c.text}</span>
              {isKey && <span className="choice-mark" aria-label="correct answer">✓</span>}
              {isWrongPick && <span className="choice-mark" aria-label="your answer">✗</span>}
            </button>
          )
        })}
      </div>

      {/* Progressive hints, same guide data the API-backed lab serves
          (spec 046). Keyed on the question so revealed depth resets with it. */}
      <SolveAssist key={question.id} questionId={question.id} graded={submitted} />

      {!submitted ? (
        <button
          type="button"
          className="btn btn-primary"
          aria-keyshortcuts="Enter"
          disabled={!selected}
          onClick={submit}
        >
          Check answer
        </button>
      ) : (
        <div className="explain" role="region" aria-label="Explanation">
          <p className={selected === shown.correct ? 'verdict verdict-ok' : 'verdict verdict-no'}>
            {selected === shown.correct
              ? 'Correct'
              : `Incorrect — the answer is ${shown.correct}`}
          </p>
          <p className="explain-body">{shown.explanation}</p>
          <ConceptRefs conceptIds={question.concepts ?? []} />
          {question.references && question.references.length > 0 && (
            <ul className="refs">
              {question.references.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  )
}
