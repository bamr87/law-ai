/** Official LSAT section length. */
export const LSAT_SECTION_SECONDS = 35 * 60

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
