/** Small presentation helpers shared across feature surfaces. */

/**
 * Compact "Xs/m/h/d ago" relative-time label. Reads the wall clock, so it is
 * client-only — render it from data fetched after mount (the standard React
 * Query path) so server and client first paint agree.
 */
export function relativeTime(d: Date): string {
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
