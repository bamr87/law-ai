'use client'

import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { resolveEffective } from '@/lib/scope/resolver'
import {
  getSettingsServerSnapshot,
  listSettingValues,
  subscribeSettings,
  upsertSettingValue,
} from '@/lib/scope/store'
import type { Effective, SettingDefinition } from '@/lib/scope/types'
import { useCallback, useSyncExternalStore } from 'react'

/**
 * Read one setting, live.
 *
 * `useSyncExternalStore` rather than a mount effect: the store is
 * localStorage-backed, so reading during render would break hydration, and a
 * one-shot effect would leave a docked widget stale until reload when the
 * preference changes from somewhere else on the page — which is exactly what
 * the timer's own "Move" menu does.
 */
export function useSetting<T>(
  def: SettingDefinition<T>,
): [T, (v: T) => void, Effective<T>] {
  const rows = useSyncExternalStore(
    subscribeSettings,
    listSettingValues,
    getSettingsServerSnapshot,
  )
  // The third element says where the value came from. The shell needs it to
  // tell "the user chose closed" from "nothing is stored" — a stored layout
  // choice wins over a route's default, an absent one does not.
  const effective = resolveEffective(def, [INSTANCE_SCOPE], rows, false)
  const value = effective.value

  const set = useCallback(
    (next: T) => {
      upsertSettingValue({
        scopeId: INSTANCE_SCOPE.id,
        key: def.key,
        value: next,
        locked: false,
      })
    },
    [def.key],
  )

  return [value, set, effective]
}
