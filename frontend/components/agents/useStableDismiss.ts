'use client'

import { useCallback, useEffect, useRef } from 'react'

/**
 * A dismiss callback whose identity never changes.
 *
 * `useFocusTrap` re-runs (and re-focuses its first control) whenever its
 * `onDismiss` identity changes, and this dashboard re-renders once a second
 * to keep relative timestamps fresh — so an inline `onClose={() => …}` prop
 * would yank focus back out of the textarea every tick (BL-20260831-07).
 */
export function useStableDismiss(onClose: () => void): () => void {
  const latest = useRef(onClose)
  useEffect(() => {
    latest.current = onClose
  }, [onClose])
  return useCallback(() => latest.current(), [])
}
