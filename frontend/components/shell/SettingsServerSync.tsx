'use client'

import { hydrateSettingValues } from '@/lib/scope/store'
import { useEffect } from 'react'

/**
 * Pull server-persisted settings once per load (BL-20260830-07).
 *
 * Renders nothing. It exists because the settings store must stay
 * DOM-and-React-free — it is read by `useSyncExternalStore` and by the server
 * render — so the one place that needs an effect lives here instead.
 *
 * For an anonymous visitor this fetch returns instance rows only and leaves
 * local writes unmirrored, so the shell behaves exactly as it did when
 * settings lived only in localStorage. A backend that is down or absent is a
 * no-op for the same reason.
 */
export default function SettingsServerSync() {
  useEffect(() => {
    void hydrateSettingValues()
  }, [])
  return null
}
