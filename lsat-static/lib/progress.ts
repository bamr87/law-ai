// Attempt tracking in localStorage (device-local, private). Matches the storage
// key used by the prior static app so existing learners keep their history.
import type { SectionCode } from './types'

export interface Attempt {
  qid: string
  section: SectionCode
  choice: string
  correct: boolean
  ts: number
}

const KEY = 'lsat-practice.attempts.v1'

function canStore(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage
}

export function getAttempts(): Attempt[] {
  if (!canStore()) return []
  try {
    const raw = window.localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Attempt[]) : []
  } catch {
    return []
  }
}

export function recordAttempt(a: Attempt): void {
  if (!canStore()) return
  try {
    const all = getAttempts()
    all.push(a)
    window.localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    /* storage full / disabled — practice still works, just not remembered */
  }
}

/**
 * Replace the whole attempt history.
 *
 * Only `backup.ts` uses this: a restore is not a sequence of new attempts, it
 * is the history the reader chose to have (BL-20260702-10).
 */
export function writeAttempts(attempts: Attempt[]): void {
  if (!canStore()) return
  try {
    window.localStorage.setItem(KEY, JSON.stringify(attempts))
  } catch {
    /* storage full / disabled */
  }
}

export function clearAttempts(): void {
  if (!canStore()) return
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* no-op */
  }
}

export interface Accuracy {
  attempted: number
  correct: number
  pct: number
}

function tally(attempts: Attempt[]): Accuracy {
  // Score each question by its most recent attempt so re-tries update accuracy.
  const latest = new Map<string, Attempt>()
  for (const a of attempts) {
    const prev = latest.get(a.qid)
    if (!prev || a.ts >= prev.ts) latest.set(a.qid, a)
  }
  const rows = [...latest.values()]
  const correct = rows.filter((r) => r.correct).length
  const attempted = rows.length
  return { attempted, correct, pct: attempted ? Math.round((correct / attempted) * 100) : 0 }
}

export function overallAccuracy(attempts: Attempt[]): Accuracy {
  return tally(attempts)
}

export function sectionAccuracy(attempts: Attempt[], section: SectionCode): Accuracy {
  return tally(attempts.filter((a) => a.section === section))
}
