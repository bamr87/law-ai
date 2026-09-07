'use client'

/**
 * The static drill's section clock.
 *
 * A *view* over `lib/lsat/timerStore` — the same module-level store the
 * platform's `SectionTimerWidget` renders, mirrored here by `make ui-sync`
 * and drift-gated by ux_audit R12 (BL-20260830-04). The two products used to
 * carry two hand-written copies of the same deadline state machine, which had
 * already forked: the static copy gained a `startAt` prop the platform's
 * lacked, and nothing would have caught the next divergence.
 *
 * What is deliberately *not* shared is the markup. The static export ships no
 * Tailwind (spec 039 NFR-PERF-1) and has no sidebar or inspector to dock
 * into, so the clock keeps its `section-timer-*` classes and its fixed place
 * in the drill head.
 */

import { useSyncExternalStore } from 'react'
import {
  averageSecondsPerQuestion,
  formatClock,
  secondsPerQuestion,
} from '@/lib/lsatTimer'
import {
  getTimerServerSnapshot,
  getTimerSnapshot,
  isSectionInProgress,
  pauseTimer,
  resetTimer,
  setTimerDuration,
  startTimer,
  subscribeTimer,
} from '@/lib/lsat/timerStore'

/**
 * Drill lengths in minutes (BL-20260829-02). 35 is a real section; 5 and 10
 * are for homework, where pacing against a full section says nothing useful.
 * The platform offers the same three from the timer's ⋯ menu.
 */
const PRESET_MINUTES = [5, 10, 35] as const

export default function SectionTimer() {
  const timer = useSyncExternalStore(
    subscribeTimer,
    getTimerSnapshot,
    getTimerServerSnapshot,
  )
  const { remainingSeconds, running } = timer
  const expired = remainingSeconds === 0
  const warn = remainingSeconds > 0 && remainingSeconds <= 5 * 60
  const urgent = remainingSeconds > 0 && remainingSeconds <= 60
  const pace = secondsPerQuestion(
    remainingSeconds,
    timer.remainingQuestions ?? 0,
  )
  const avg = averageSecondsPerQuestion(timer.answeredSeconds, timer.answered)
  const tone = expired || urgent ? 'urgent' : warn ? 'warn' : ''
  const inProgress = isSectionInProgress(timer)

  return (
    <div className="section-timer">
      <div className="section-timer-readout">
        <span className="section-timer-label">Section timer</span>
        <span
          role="timer"
          aria-label="Section time remaining"
          className={'section-timer-clock' + (tone ? ` section-timer-${tone}` : '')}
        >
          {formatClock(remainingSeconds)}
        </span>
        {expired && (
          <span className="section-timer-expired" role="status">
            Time&apos;s up — you can keep practicing
          </span>
        )}
        {!expired && pace != null && (
          <span className="section-timer-pace" aria-label="Time remaining per question">
            {formatClock(pace)} left / q
          </span>
        )}
        {avg != null && (
          <span className="section-timer-avg" aria-label="Average time per question">
            avg {formatClock(avg)} / q
          </span>
        )}
      </div>
      {/* Locked while a section is under way: changing the length mid-run
          would throw away the time already spent, and a student who wants
          that has Reset. */}
      <div
        className="section-timer-presets"
        role="radiogroup"
        aria-label="Drill length"
      >
        {PRESET_MINUTES.map((m) => (
          <button
            key={m}
            type="button"
            className="btn"
            role="radio"
            aria-checked={timer.durationSeconds === m * 60}
            disabled={inProgress}
            onClick={() => setTimerDuration(m * 60)}
          >
            {m} min
          </button>
        ))}
      </div>
      <div className="section-timer-controls">
        {!expired && (
          <button
            type="button"
            className="btn"
            onClick={() => (running ? pauseTimer() : startTimer())}
          >
            {running ? 'Pause' : 'Start'}
          </button>
        )}
        <button type="button" className="btn" onClick={() => resetTimer()}>
          Reset
        </button>
      </div>
    </div>
  )
}
