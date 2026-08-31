'use client'

import { useEffect, useRef, useState } from 'react'

import {
  averageSecondsPerQuestion,
  formatClock,
  LSAT_SECTION_SECONDS,
  secondsPerQuestion,
} from '@/lib/lsatTimer'

export default function LsatTimer({
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
  const clockClass =
    'font-mono text-lg tabular-nums ' +
    (expired
      ? 'text-red-300'
      : urgent
        ? 'text-red-300'
        : warn
          ? 'text-amber-300'
          : 'text-slate-100')

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">
          Section timer
        </div>
        <div className="flex items-baseline gap-2">
          <span role="timer" aria-label="Section time remaining" className={clockClass}>
            {formatClock(remaining)}
          </span>
          {expired && (
            <span className="text-xs font-medium text-red-300" role="status">
              Time&apos;s up — you can keep practicing
            </span>
          )}
          {!expired && pace != null && (
            <span
              className="text-xs tabular-nums text-slate-500"
              aria-label="Time remaining per question"
            >
              {formatClock(pace)} left / q
            </span>
          )}
          {avg != null && (
            <span
              className="text-xs tabular-nums text-slate-300"
              aria-label="Average time per question"
            >
              avg {formatClock(avg)} / q
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        {!expired && (
          <button
            type="button"
            onClick={() =>
              setDeadline(running ? null : Date.now() + remaining * 1000)
            }
            className="rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[11px] font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            {running ? 'Pause' : 'Start'}
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setDeadline(null)
            setRemaining(durationSeconds)
          }}
          className="rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[11px] font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
        >
          Reset
        </button>
      </div>
    </div>
  )
}

export function QuestionElapsed({
  frozen,
  onTick,
}: {
  frozen: boolean
  onTick?: (seconds: number) => void
}) {
  const [elapsed, setElapsed] = useState(0)
  const elapsedRef = useRef(0)
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
    <span
      className="ml-auto font-mono text-[11px] tabular-nums text-slate-400"
      aria-label="Time on this question"
    >
      {formatClock(elapsed)}
    </span>
  )
}
