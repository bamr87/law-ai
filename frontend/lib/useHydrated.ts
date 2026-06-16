'use client'

import { useSyncExternalStore } from 'react'

const noopSubscribe = () => () => {}

/**
 * Returns `false` on the server and on the client's first (hydration) render,
 * then `true` after mount. Gate live/client-only values behind this so the
 * initial client render matches the server HTML — otherwise fast localhost
 * queries (React Query) resolve before hydration commits and trip a
 * hydration mismatch.
 *
 * Uses `useSyncExternalStore` (the React-recommended hydration check) so the
 * server snapshot is `false` and the client snapshot is `true` with no
 * set-state-in-effect.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  )
}
