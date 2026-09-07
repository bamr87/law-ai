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

/**
 * Who the server rendered *as* (BL-20260905-10).
 *
 * Layout rows live at `user:<pk>` for a signed-in visitor, and a resolver that
 * does not know the id walks `[instance]` and skips every one of them. The id
 * reaches the server render through its own cookie and stays available to the
 * hydration render, so both resolve the chain the client will — otherwise the
 * user's layout is absent from the first paint and reflows in after mount.
 */
const SettingsScopeContext = createContext<string | null>(null)

export function SettingsSnapshotProvider({
  rows,
  userScopeId,
  children,
}: {
  rows?: SettingValue[]
  userScopeId?: string | null
  children: ReactNode
}) {
  const value = rows && rows.length > 0 ? rows : NO_ROWS

  useEffect(() => {
    reconcileSettingsCookie()
  }, [])

  return (
    <SettingsSnapshotContext.Provider value={value}>
      <SettingsScopeContext.Provider value={userScopeId ?? null}>
        {children}
      </SettingsScopeContext.Provider>
    </SettingsSnapshotContext.Provider>
  )
}

/** The server-rendered rows, or the stable empty list outside a provider. */
export function useSettingsSnapshot(): SettingValue[] {
  return useContext(SettingsSnapshotContext)
}

/** The scope id the server rendered with, or `null` outside a provider. */
export function useSettingsSnapshotScope(): string | null {
  return useContext(SettingsScopeContext)
}
