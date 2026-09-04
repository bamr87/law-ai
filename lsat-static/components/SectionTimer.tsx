'use client'

import { useEffect, useRef, useState } from 'react'
import {
  averageSecondsPerQuestion,
  formatClock,
  LSAT_SECTION_SECONDS,
  secondsPerQuestion,
} from '@/lib/timer'

export default function SectionTimer({
  remainingQuestions,
  answeredCount = 0,
  answeredSeconds = 0,
  durationSeconds = LSAT_SECTION_SECONDS,
}: {
  remainingQuestions?: number
  answeredCount?: number
  answeredSeconds?: number
  durationSeconds?: number
}) {
  const [remaining, setRemaining] = useState(durationSeconds)
  const [deadline, setDeadline] = useState<number | null>(null)

  useEffect(() => {
    if (deadline == null) return
    const id = window.setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      setRemaining(left)
      if (left === 0) setDeadline(null)
    }, 250)
    return () => window.clearInterval(id)
  }, [deadline])

  const running = deadline != null
  const expired = remaining === 0
  const warn = remaining > 0 && remaining <= 5 * 60
  const urgent = remaining > 0 && remaining <= 60
  const pace = secondsPerQuestion(remaining, remainingQuestions ?? 0)
  const avg = averageSecondsPerQuestion(answeredSeconds, answeredCount)
  const tone = expired || urgent ? 'urgent' : warn ? 'warn' : ''

  return (
    <div className="section-timer">
      <div className="section-timer-readout">
        <span className="section-timer-label">Section timer</span>
        <span
          role="timer"
          aria-label="Section time remaining"
          className={'section-timer-clock' + (tone ? ` section-timer-${tone}` : '')}
        >
          {formatClock(remaining)}
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
      <div className="section-timer-controls">
        {!expired && (
          <button
            type="button"
            className="btn"
            onClick={() =>
              setDeadline(running ? null : Date.now() + remaining * 1000)
            }
          >
            {running ? 'Pause' : 'Start'}
          </button>
        )}
        <button
          type="button"
          className="btn"
          onClick={() => {
            setDeadline(null)
            setRemaining(durationSeconds)
          }}
        >
          Reset
        </button>
      </div>
    </div>
  )
}

export function QuestionElapsed({
  frozen,
  startAt = 0,
  onTick,
}: {
  frozen: boolean
  /**
   * Seconds already banked against this question. The drill passes the time a
   * revisited question was answered in, so paging back does not claim you
   * solved it in 0:00.
   */
  startAt?: number
  onTick?: (seconds: number) => void
}) {
  const [elapsed, setElapsed] = useState(startAt)
  const elapsedRef = useRef(startAt)
  const onTickRef = useRef(onTick)
  useEffect(() => {
    onTickRef.current = onTick
  }, [onTick])

  useEffect(() => {
    if (frozen) {
      onTickRef.current?.(elapsedRef.current)
      return
    }
    const started = Date.now() - elapsedRef.current * 1000
    const id = window.setInterval(() => {
      const next = Math.floor((Date.now() - started) / 1000)
      elapsedRef.current = next
      setElapsed(next)
      onTickRef.current?.(next)
    }, 250)
    return () => window.clearInterval(id)
  }, [frozen])

  return (
    <span className="qcard-elapsed" aria-label="Time on this question">
      {formatClock(elapsed)}
    </span>
  )
}
