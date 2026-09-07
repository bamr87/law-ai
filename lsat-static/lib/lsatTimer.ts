/** Official LSAT section length. */
export const LSAT_SECTION_SECONDS = 35 * 60

/**
 * Items in a real scored section, and so the denominator a pace readout is
 * allowed to quote (BL-20260905-32).
 *
 * The Logical Reasoning drill deals one question at a time out of a bank that
 * is already in the hundreds, and it used to publish `bank - graded` as
 * "remaining". Against the 35-minute clock that quoted an 8-second-per-
 * question pace: arithmetically true, and meaningless as practice advice. A
 * section is 25 items, so that — capped by a bank too small to fill one — is
 * what the clock paces against.
 */
export const LSAT_SECTION_QUESTIONS = 25

/**
 * Format a duration as `M:SS` (or `H:MM:SS` past an hour).
 *
 * @example
 * formatClock(84) // "1:24"
 * formatClock(0) // "0:00"
 */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(s / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  const seconds = s % 60
  const mm = hours > 0 ? String(minutes).padStart(2, '0') : String(minutes)
  const ss = String(seconds).padStart(2, '0')
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

/**
 * Remaining time per remaining question, or null when pacing is undefined.
 *
 * @example
 * secondsPerQuestion(2100, 25) // 84
 * secondsPerQuestion(0, 5) // null
 */
export function secondsPerQuestion(
  remainingSeconds: number,
  remainingQuestions: number,
): number | null {
  if (remainingQuestions <= 0 || remainingSeconds <= 0) return null
  return remainingSeconds / remainingQuestions
}

/**
 * Actual seconds per answered question, or null before the first answer.
 *
 * @example
 * averageSecondsPerQuestion(168, 2) // 84
 * averageSecondsPerQuestion(10, 0) // null
 */
export function averageSecondsPerQuestion(
  totalSeconds: number,
  answeredCount: number,
): number | null {
  if (answeredCount <= 0) return null
  return Math.max(0, totalSeconds) / answeredCount
}
