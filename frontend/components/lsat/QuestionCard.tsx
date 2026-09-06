'use client'

/**
 * Question card — one LSAT item with its answer radiogroup, grading, the
 * solve guide, and the post-grade tutor / cross-check surfaces. Used by every
 * drill section (LR isolated, RC/LG stacked under a passage).
 *
 * Moved out of `LsatLab.tsx` in phase 1 of BL-20260830-02. Its counterpart
 * is `lsat-static/components/QuestionCard.tsx`; the two share the keyboard
 * contract (one tab stop, arrows move and select, letters pick, Enter
 * submits) and differ only in what happens after grading.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import {
  gradeLsat,
  type LsatChoiceLabel,
  type LsatGradeResponse,
  type LsatQuestion,
} from '@/lib/api'
import { QuestionElapsed } from '@/components/LsatTimer'
import ConceptRefs from '@/components/lsat/ConceptRefs'
import CrossCheckPanel from '@/components/lsat/CrossCheckPanel'
import { DiffBadge } from '@/components/lsat/LabPrimitives'
import SolveAssist from '@/components/lsat/SolveAssist'
import TutorPane from '@/components/lsat/TutorPane'

export default function QuestionCard({
  question,
  onResolved,
  onNext,
  compact,
  elapsedEnabled = true,
  onActivate,
  cardRef,
}: {
  question: LsatQuestion
  onResolved: (
    r: LsatGradeResponse,
    elapsedSeconds: number,
    hintsUsed?: number,
  ) => void
  onNext?: () => void
  compact?: boolean
  elapsedEnabled?: boolean
  onActivate?: () => void
  /** Focus target the panel moves to when it swaps in a new question. */
  cardRef?: React.Ref<HTMLDivElement>
}) {
  const [selected, setSelected] = useState<LsatChoiceLabel | null>(null)
  const [result, setResult] = useState<LsatGradeResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTutor, setShowTutor] = useState(false)
  const [walkthrough, setWalkthrough] = useState(false)
  const elapsedRef = useRef(0)
  const hintsUsedRef = useRef(0)

  // One tab stop for the whole choice list, arrows move and select within it —
  // the same pattern `lsat-static/components/QuestionCard.tsx` has always had.
  // Under exam-style time pressure, tabbing through five choices to reach the
  // submit button is a real cost, and it was the platform's alone to pay.
  const choiceRoving = useRovingTabIndex({
    count: question.choices.length,
    activeIndex: selected
      ? question.choices.findIndex((c) => c.label === selected)
      : -1,
    orientation: 'vertical',
    onActivate: (i) => {
      if (result === null) setSelected(question.choices[i].label)
    },
  })

  // Reset when the question changes.
  useEffect(() => {
    setSelected(null)
    setResult(null)
    setShowTutor(false)
    setWalkthrough(false)
    setError(null)
    elapsedRef.current = 0
    hintsUsedRef.current = 0
  }, [question.id])

  const onHintsUsedChange = useCallback((n: number) => {
    hintsUsedRef.current = n
  }, [])
  const openWalkthrough = useCallback(() => setWalkthrough(true), [])

  const submit = async () => {
    if (!selected || submitting) return
    const elapsed = elapsedRef.current
    const hintsUsed = hintsUsedRef.current
    setSubmitting(true)
    setError(null)
    try {
      const r = await gradeLsat(question.id, selected, hintsUsed)
      setResult(r)
      onResolved(r, elapsed, hintsUsed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Grade failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Keyboard drilling: A–E pick a choice, Enter submits, then N (or Enter
  // again) draws the next question. Scoped to the card (events bubble from the
  // focused choice buttons) so stacked RC/LG cards never react to one
  // another's keypresses, and we ignore keys typed into the tutor's text
  // input.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (submitting) return
    // Let modified shortcuts (Ctrl/⌘/Alt+key, e.g. Select All) reach the browser.
    if (e.ctrlKey || e.metaKey || e.altKey) return
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    const key = e.key.toUpperCase()
    if (result) {
      // Graded: the only move left is forward, and it was two Tab stops away
      // past the hint carousel — far enough that a timed drill reached for the
      // mouse instead.
      if (onNext && (key === 'N' || e.key === 'Enter')) {
        e.preventDefault()
        onNext()
      }
      return
    }
    if (['A', 'B', 'C', 'D', 'E'].includes(key)) {
      if (question.choices.some((c) => c.label === key)) {
        setSelected(key as LsatChoiceLabel)
        e.preventDefault()
      }
    } else if (e.key === 'Enter' && selected) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <div
      ref={cardRef}
      // Programmatic focus target. Every shortcut on this card is bound to
      // this element, so focus leaving it silently disarms the whole keyboard
      // drill — which is exactly what a fresh question did until the panel
      // started moving focus back in.
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      onFocusCapture={onActivate}
      onPointerDown={onActivate}
      className={
        'rounded-2xl border border-slate-800 bg-slate-900/40 backdrop-blur focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ' +
        (compact ? 'p-4' : 'p-6')
      }
    >
      {/* Persistent live region so screen readers announce the grade result. */}
      <p className="sr-only" role="status" aria-live="polite">
        {result
          ? result.correct
            ? 'Correct.'
            : `Incorrect. The correct answer was ${result.correct_choice}.`
          : ''}
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="font-mono text-slate-400">{question.id}</span>
        <span className="text-slate-700">·</span>
        <span>{question.section}</span>
        <span className="text-slate-700">·</span>
        <DiffBadge difficulty={question.difficulty} />
        {question.concepts && question.concepts.length > 0 && (
          <>
            <span className="text-slate-700">·</span>
            <span className="normal-case text-slate-400">
              {question.concepts.slice(0, 3).join(' · ')}
            </span>
          </>
        )}
        <QuestionElapsed
          key={question.id}
          frozen={result !== null || submitting || !elapsedEnabled}
          onTick={(s) => {
            elapsedRef.current = s
          }}
        />
      </div>

      <p className="whitespace-pre-line text-base leading-relaxed text-slate-100">
        {question.stem}
      </p>

      <ul
        className="mt-5 space-y-2"
        role="radiogroup"
        aria-label="Answer choices"
      >
        {question.choices.map((c, i) => {
          const isSelected = selected === c.label
          const showResult = result !== null
          const isCorrect = showResult && c.label === result.correct_choice
          const isWrongPick =
            showResult && isSelected && c.label !== result.correct_choice
          let cls =
            'group flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-sm transition '
          if (showResult) {
            // Still focusable (see aria-disabled below), so it has to stop
            // advertising itself as clickable.
            cls += 'cursor-default '
            if (isCorrect)
              cls += 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100'
            else if (isWrongPick)
              cls += 'border-red-500/50 bg-red-500/10 text-red-100'
            else cls += 'border-slate-800 bg-slate-950/40 text-slate-400'
          } else if (isSelected) {
            cls += 'border-blue-500/60 bg-blue-500/10 text-blue-100'
          } else {
            cls +=
              'border-slate-800 bg-slate-950/40 text-slate-200 hover:border-slate-600 hover:bg-slate-900/60'
          }
          return (
            <li key={c.label}>
              <button
                type="button"
                {...choiceRoving.itemProps(i)}
                role="radio"
                aria-checked={isSelected}
                // `aria-disabled`, not `disabled`: a disabled button leaves the
                // focus order, so grading while a choice had focus dropped
                // focus to <body> — outside this card, where none of the
                // shortcuts above can hear a keystroke any more.
                aria-disabled={showResult}
                onClick={() => {
                  if (!showResult) setSelected(c.label)
                }}
                className={cls}
              >
                {/* The letter stays in the accessible name on purpose. The
                  * static site hides it, but in a drill the letter *is* the
                  * answer's identity — it is what a student records and what
                  * the tutor refers back to. "Alpha" alone loses that. */}
                <span
                  className={
                    'mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ' +
                    (isSelected || isCorrect
                      ? 'border-current'
                      : 'border-slate-700 text-slate-400 group-hover:border-slate-500')
                  }
                >
                  {c.label}
                </span>
                <span>{c.text}</span>
              </button>
            </li>
          )
        })}
      </ul>

      {result && onNext && (
        <p className="mt-2 text-[11px] text-slate-500">
          Keyboard:{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            N
          </kbd>{' '}
          or{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            Enter
          </kbd>{' '}
          for the next question
        </p>
      )}

      {!result && (
        <p className="mt-2 text-[11px] text-slate-500">
          Keyboard:{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            A
          </kbd>
          –
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            E
          </kbd>{' '}
          to choose ·{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            Enter
          </kbd>{' '}
          to submit
        </p>
      )}

      {/* Spec 045 FR-6: progressive solve guide (hints + diagrams). */}
      <SolveAssist
        key={question.id}
        questionId={question.id}
        graded={result !== null}
        onHintsUsedChange={onHintsUsedChange}
        onAskTutor={openWalkthrough}
      />

      {walkthrough && !result && (
        <TutorPane
          questionId={question.id}
          userChoice={selected}
          initialQuestion="Walk me through the setup step by step without revealing the answer."
        />
      )}

      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {!result && (
          <button
            onClick={() => void submit()}
            disabled={!selected || submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {submitting ? 'Grading…' : 'Submit'}
          </button>
        )}
        {result && (
          <>
            <span
              className={
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ' +
                (result.correct
                  ? 'bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-500/30'
                  : 'bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-500/30')
              }
            >
              {result.correct
                ? 'Correct'
                : `Incorrect — answer was ${result.correct_choice}`}
            </span>
            <button
              onClick={() => setShowTutor((v) => !v)}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20"
            >
              {showTutor ? 'Hide AI Tutor' : 'Ask AI Tutor'}
            </button>
            {onNext && (
              <button
                onClick={onNext}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
              >
                Next →
              </button>
            )}
          </>
        )}
      </div>

      {/* Post-grade references point only at the in-app concept catalog —
          the author-rationale block with external source links was removed
          deliberately (spec 045 FR-12). Method teaching lives in SolveAssist
          and the AI tutor. */}
      {result && (
        <ConceptRefs
          conceptIds={Array.from(
            new Set([...(result.concepts ?? []), ...(question.concepts ?? [])]),
          )}
        />
      )}

      {/* Spec 045 FR-14: independent blind solve vs. the answer key. */}
      {result && <CrossCheckPanel questionId={question.id} />}

      {showTutor && result && (
        <TutorPane
          questionId={question.id}
          userChoice={selected}
        />
      )}
    </div>
  )
}
