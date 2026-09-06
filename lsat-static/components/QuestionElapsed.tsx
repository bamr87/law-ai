'use client'

/**
 * Per-question stopwatch for the static drill.
 *
 * Split out of `SectionTimer.tsx` so the file name says what it renders: the
 * section clock and the per-question stopwatch are different widgets with
 * different lifetimes, and bundling them under one timer name is the same
 * naming confusion the platform side just unwound (BL-20260831-15).
 *
 * Mirrors `frontend/components/lsat/QuestionElapsed.tsx` — same state machine
 * and the same `frozen`/`startAt`/`onTick` contract, over the same
 * `lib/lsatTimer` helpers. Only the presentation differs: this export ships no
 * Tailwind, so it styles with `qcard-elapsed`.
 */

import { useEffect, useRef, useState } from 'react'
import { formatClock } from '@/lib/lsatTimer'

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

export default QuestionElapsed
