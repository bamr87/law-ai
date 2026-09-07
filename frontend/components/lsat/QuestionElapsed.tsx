'use client'

/**
 * Per-question stopwatch.
 *
 * This used to live in `components/LsatTimer.tsx` next to a second, entirely
 * separate section clock. That file's default export died when spec 043 moved
 * the section clock into the dockable `SectionTimerWidget`, and the leftover
 * name was actively misleading: "LsatTimer" was not the LSAT timer. The clock
 * a learner sees is `SectionTimerWidget` over `lib/lsat/timerStore`; this is
 * the small elapsed readout inside a question card, and it belongs next to the
 * card (BL-20260831-15).
 *
 * The static drill has a matching copy at
 * `lsat-static/components/QuestionElapsed.tsx` — same state machine, same
 * `frozen`/`startAt`/`onTick` contract, over the same `lib/lsatTimer` helpers
 * (a `make ui-sync` mirror). Only the presentation layer differs: Tailwind
 * here, `qcard-elapsed` there, because the static export ships no Tailwind.
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
   * Seconds already banked against this question. A drill paging back over
   * ground it has covered passes the time the question was answered in, so a
   * revisit does not claim you solved it in 0:00.
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
    <span
      className="ml-auto font-mono text-[11px] tabular-nums text-slate-400"
      aria-label="Time on this question"
    >
      {formatClock(elapsed)}
    </span>
  )
}

export default QuestionElapsed
