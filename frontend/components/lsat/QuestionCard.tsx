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

import { usePageShortcuts } from '@/components/shell/PageShortcuts'
import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import { LSAT_DRILL_SHORTCUTS } from '@/components/lsat/drillShortcuts'
import { useShortcuts, type ShortcutMap } from '@/lib/lsat/keyboard'
import {
  gradeLsat,
  type LsatChoiceLabel,
  type LsatGradeResponse,
  type LsatQuestion,
  type LsatTutorTrace,
} from '@/lib/api'
import ConceptRefs from '@/components/lsat/ConceptRefs'
import CrossCheckPanel from '@/components/lsat/CrossCheckPanel'
import { DiffBadge } from '@/components/lsat/LabPrimitives'
import { QuestionElapsed } from '@/components/lsat/QuestionElapsed'
import SolveAssist from '@/components/lsat/SolveAssist'
import TutorPane from '@/components/lsat/TutorPane'

/**
 * What a panel has to hold on a learner's behalf when it swaps this card out
 * for another one. The card is keyed on the question, so everything it owns is
 * destroyed on the way past — mirroring `lsat-static`'s `Drill.Answer`, which
 * exists for the same reason (BL-20260901-08).
 */
export interface SavedAnswer {
  choice: LsatChoiceLabel
  result: LsatGradeResponse
  elapsedSeconds: number
}

export default function QuestionCard({
  question,
  onResolved,
  onNext,
  onPrev,
  browsable = false,
  saved,
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
    /**
     * The label the learner picked. The grade response names only the *correct*
     * choice, so a panel that has to restore this card later (RC/LG) cannot
     * recover the pick from it.
     */
    choice?: LsatChoiceLabel,
  ) => void
  onNext?: () => void
  /** Step back one question — only a fixed stack (RC/LG) has one. */
  onPrev?: () => void
  /**
   * This question sits in a *fixed* stack the learner can move around in
   * (RC/LG), rather than a stream dealt one at a time (LR). In a stack `N` may
   * skip forward before grading, because the question skipped is still there
   * to come back to; in a stream it must not be, because it is not.
   */
  browsable?: boolean
  /** A graded answer this panel is holding for the question (BL-20260901-08). */
  saved?: SavedAnswer | null
  compact?: boolean
  elapsedEnabled?: boolean
  onActivate?: () => void
  /** Focus target the panel moves to when it swaps in a new question. */
  cardRef?: React.Ref<HTMLDivElement>
}) {
  const [selected, setSelected] = useState<LsatChoiceLabel | null>(
    saved?.choice ?? null,
  )
  const [result, setResult] = useState<LsatGradeResponse | null>(
    saved?.result ?? null,
  )
  // Choices the learner has crossed out on this attempt (BL-20260429-18).
  // Local to the attempt on purpose: it is reasoning in progress, not a graded
  // answer, so it resets with the question and is never persisted.
  const [eliminated, setEliminated] = useState<LsatChoiceLabel[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTutor, setShowTutor] = useState(false)
  const [walkthrough, setWalkthrough] = useState(false)
  const elapsedRef = useRef(saved?.elapsedSeconds ?? 0)
  const hintsUsedRef = useRef(0)
  // Read through a ref inside the reset effect below: a panel rebuilds the
  // saved-answer object on every render, and depending on it directly would
  // reset the card mid-question.
  const savedRef = useRef(saved)
  useEffect(() => {
    savedRef.current = saved
  })

  // Publish this card's keys to the shell's `?` sheet while it is on screen
  // (BL-20260901-10): the drill's letters and Enter were discoverable only
  // from the card's own hint line.
  usePageShortcuts(LSAT_DRILL_SHORTCUTS)

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

  // Reset when the question changes — back to whatever the panel has saved for
  // the new question, so stepping back through a passage stack shows the
  // answers you already gave rather than a blank card.
  useEffect(() => {
    const s = savedRef.current
    setSelected(s?.choice ?? null)
    setEliminated([])
    setResult(s?.result ?? null)
    setShowTutor(false)
    setWalkthrough(false)
    setError(null)
    elapsedRef.current = s?.elapsedSeconds ?? 0
    hintsUsedRef.current = 0
  }, [question.id])

  /**
   * The attempt trace the tutor coaches against (BL-20260429-18).
   *
   * A callback, not a value, and deliberately unmemoized: it reads refs that
   * move as the learner works, so the tutor is told what they had done *when
   * they asked* rather than what the card knew when the pane mounted. Nothing
   * downstream keys off its identity.
   */
  const attemptTrace = (): LsatTutorTrace => ({
    ...(eliminated.length > 0 ? { eliminated } : {}),
    hints_used: hintsUsedRef.current,
    seconds_on_question: Math.round(elapsedRef.current),
    ...(saved?.choice ? { prior_choices: [saved.choice] } : {}),
  })

  /**
   * Rule a choice in or out (BL-20260429-18).
   *
   * Elimination is how the section is actually solved, and until this existed
   * the tutor only ever heard timing and hint counts — metadata about an
   * attempt, not the reasoning inside it. Crossing a choice out here is what
   * puts "you ruled out the key" in reach of the coaching.
   */
  const toggleEliminated = (label: LsatChoiceLabel) => {
    if (result || submitting) return
    setEliminated((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label],
    )
  }

  /** The choice `X` acts on: the one with focus, else the selected one. */
  const focusedLabel = (): LsatChoiceLabel | null => {
    const radio =
      typeof document !== 'undefined'
        ? (document.activeElement as HTMLElement | null)?.closest?.(
            '[role="radio"]',
          )
        : null
    const label = radio?.getAttribute('data-choice') ?? selected
    return (label as LsatChoiceLabel | null) ?? null
  }

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
      // `question.remap` is the signed order this serve used, when the
      // choices were shuffled (BL-20260606-01); the grader needs it to read
      // the picked label back into the stored one.
      const r = await gradeLsat(
        question.id,
        selected,
        hintsUsed,
        question.remap,
      )
      setResult(r)
      onResolved(r, elapsed, hintsUsed, selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Grade failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Pick a choice by its letter, moving focus with it — exactly as the static
  // drill's `focusLabel` does. Selecting without moving focus left the two out
  // of step, and then Enter — read below off the *focused* choice — meant a
  // different answer from the one showing as checked (BL-20260702-13).
  const pickLabel = (label: string) => {
    if (result || submitting) return
    const i = question.choices.findIndex((c) => c.label === label)
    if (i < 0) return
    setSelected(label as LsatChoiceLabel)
    choiceRoving.focusItem(i)
  }

  // The drill's keys, bound at the window (BL-20260901-06) through the same
  // module the static site uses. They were scoped to this card's DOM subtree,
  // which meant none of them did anything until you had tabbed or clicked into
  // it — the platform asked for a hand on the mouse to start a drill the
  // static site started from the keyboard. Stacked cards were the reason for
  // the old scoping and there are none any more: every panel renders exactly
  // one question (BL-20260901-08).
  //
  // `Enter` deliberately stays on the card handler below. A window binding
  // has to `preventDefault()` before it can run, and Enter is the key every
  // button on the page already answers — swallowing it would break "Ask AI
  // Tutor", "Show final step" and the jump strip for keyboard users.
  const keymap: ShortcutMap = {}
  for (const c of question.choices) {
    keymap[c.label.toLowerCase()] = () => pickLabel(c.label)
  }
  // `N` moves forward once the question is graded, and — in a fixed stack —
  // before that too, so a hard question can be skipped and come back to. A
  // dealt stream (LR) must not: the question it would deal is not the one that
  // was skipped, so there is no coming back.
  // `X` crosses out the focused choice — the keyboard half of the elimination
  // control below, so a drill run entirely from the keyboard can still tell
  // the tutor what it ruled out (BL-20260429-18).
  keymap.x = () => {
    const label = focusedLabel()
    if (label) toggleEliminated(label)
  }
  if (onNext && (result !== null || browsable)) keymap.n = () => onNext()
  // `P` steps back whenever there is anything to step back to, graded or not.
  if (onPrev) keymap.p = () => onPrev()
  useShortcuts(keymap, { enabled: !submitting })

  // Enter, scoped to this card: on a radio that is not the selected one it
  // selects that choice rather than grading another; anywhere else on the card
  // it submits the selection, and once graded it draws the next question.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (submitting || e.key !== 'Enter') return
    // Let modified shortcuts (Ctrl/⌘/Alt+key) reach the browser.
    if (e.ctrlKey || e.metaKey || e.altKey) return
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    // Every other button on the card answers Enter itself — "Ask AI Tutor",
    // "Show final step", the jump strip. Taking Enter from them would make
    // them mouse-only. The choices are buttons too, and they are the one kind
    // this card does own.
    const button = (e.target as HTMLElement).closest?.('button')
    const onOtherControl = Boolean(
      button && button.getAttribute('role') !== 'radio',
    )
    if (result) {
      // Graded: the only move left is forward, and it was two Tab stops away
      // past the hint carousel — far enough that a timed drill reached for the
      // mouse instead.
      if (onNext && !onOtherControl) {
        e.preventDefault()
        onNext()
      }
      return
    }
    if (onOtherControl) return
    const focused = (e.target as HTMLElement).closest?.('[role="radio"]')
    const label = focused?.getAttribute('data-choice') ?? null
    if (label !== null && label !== selected) {
      e.preventDefault()
      setSelected(label as LsatChoiceLabel)
    } else if (selected) {
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
          const isEliminated = eliminated.includes(c.label)
          if (isEliminated && !showResult) cls += ' line-through opacity-50'
          return (
            <li key={c.label} className="flex items-start gap-2">
              <button
                type="button"
                {...choiceRoving.itemProps(i)}
                role="radio"
                // The card-level Enter handler reads the focused choice back
                // off this, so it can never grade a choice other than the one
                // the cursor is on (BL-20260702-13).
                data-choice={c.label}
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
              {!showResult && (
                <button
                  type="button"
                  onClick={() => toggleEliminated(c.label)}
                  aria-pressed={isEliminated}
                  aria-label={
                    (isEliminated ? 'Restore choice ' : 'Rule out choice ') +
                    c.label
                  }
                  title={`Rule out ${c.label} (X)`}
                  className={
                    'mt-1 shrink-0 rounded-md border px-2 py-1 text-xs transition focus-ring ' +
                    (isEliminated
                      ? 'border-amber-500/50 bg-amber-500/10 text-amber-200'
                      : 'border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300')
                  }
                >
                  ✗
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {!result && (
        <p className="mt-2 text-[11px] text-slate-500">
          Cross out a choice with{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            X
          </kbd>{' '}
          or ✗ — the tutor coaches against what you ruled out.
        </p>
      )}

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
          {onPrev && (
            <>
              {' · '}
              <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
                P
              </kbd>{' '}
              for the previous one
            </>
          )}
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
          {browsable && (
            <>
              {' · '}
              <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
                N
              </kbd>
              /
              <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
                P
              </kbd>{' '}
              to move between questions
            </>
          )}
        </p>
      )}

      {/* Spec 045 FR-6: progressive solve guide (hints + diagrams). */}
      <SolveAssist
        key={question.id}
        questionId={question.id}
        graded={result !== null}
        onHintsUsedChange={onHintsUsedChange}
        onAskTutor={openWalkthrough}
        remap={question.remap}
      />

      {walkthrough && !result && (
        <TutorPane
          questionId={question.id}
          userChoice={selected}
          initialQuestion="Walk me through the setup step by step without revealing the answer."
          trace={attemptTrace}
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
          trace={attemptTrace}
        />
      )}
    </div>
  )
}
