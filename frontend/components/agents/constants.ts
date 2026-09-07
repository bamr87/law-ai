'use client'

/** Poll cadences and panel sizes shared by the dashboard and its parts. */

export const POLL_MS = 5000

/**
 * Poll interval once the ops push channel is live (BL-20260429-16).
 *
 * The socket is an optimisation, not a source of truth, so polling never
 * stops entirely — it drops to a slow safety net that catches anything the
 * push missed (a dropped frame, a change made by a process that does not
 * notify). When the socket is down we are back to the original 5s cadence.
 */
export const FALLBACK_POLL_MS = 30_000

/** How many gap rows the ops card shows (the cycle only drafts the top one). */
export const GAP_ROWS = 3
