'use client'

import { reconcileSettingsCookie } from '@/lib/scope/store'
import { NO_ROWS } from '@/lib/scope/rows'
import type { SettingValue } from '@/lib/scope/types'
import { createContext, useContext, useEffect, type ReactNode } from 'react'

/**
 * The setting rows the *server* rendered with (BL-20260905-09).
 *
 * `useSetting` reads localStorage through `useSyncExternalStore`, which the
 * server cannot see — so before this, a non-default layout (rail hidden,
 * sidebar on the right) painted the default first and reflowed on every full
 * load. The store mirrors its rows into a cookie; `app/(app)/layout.tsx` reads
 * that cookie on the server and hands the rows down here, and React uses them
 * as the `getServerSnapshot` value for both the server render and the
 * hydration render — so the two agree by construction and the chosen layout is
 * on the first paint.
 *
 * localStorage remains the source of truth once hydrated. The two can only
 * drift if one is cleared alone, so the provider rewrites the cookie from
 * localStorage after mount: at worst one load reflows, and the next is right.
 */
const SettingsSnapshotContext = createContext<SettingValue[]>(NO_ROWS)

export function SettingsSnapshotProvider({
  rows,
  children,
}: {
  rows?: SettingValue[]
  children: ReactNode
}) {
  const value = rows && rows.length > 0 ? rows : NO_ROWS

  useEffect(() => {
    reconcileSettingsCookie()
  }, [])

  return (
    <SettingsSnapshotContext.Provider value={value}>
      {children}
    </SettingsSnapshotContext.Provider>
  )
}

/** The server-rendered rows, or the stable empty list outside a provider. */
export function useSettingsSnapshot(): SettingValue[] {
  return useContext(SettingsSnapshotContext)
}
