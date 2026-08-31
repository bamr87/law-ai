'use client'

import { useEffect, useState } from 'react'

/**
 * Viewport predicate for layout decisions React has to make in JS — chiefly
 * "is this panel a docked column or an off-canvas drawer", which changes the
 * *markup*, not just the styling, and so cannot be done in CSS alone.
 *
 * Always starts `false` and updates after mount: the server has no viewport,
 * and guessing one produces a hydration mismatch on every phone.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mql = window.matchMedia(query)
    const update = () => setMatches(mql.matches)
    update()
    // Safari < 14 only has the deprecated listener API.
    if (mql.addEventListener) {
      mql.addEventListener('change', update)
      return () => mql.removeEventListener('change', update)
    }
    mql.addListener(update)
    return () => mql.removeListener(update)
  }, [query])

  return matches
}

/** Below `md` — the rail becomes a bottom tab bar and panels become drawers. */
export const COMPACT_QUERY = '(max-width: 767px)'
/** Below `lg` — not enough room for a third column. */
export const NARROW_QUERY = '(max-width: 1023px)'
