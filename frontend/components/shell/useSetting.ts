'use client'

import {
  INSTANCE_SCOPE,
  settingsChain,
  userScopeFor,
} from '@/lib/scope/instance'
import { resolveEffective } from '@/lib/scope/resolver'
import {
  listSettingValues,
  serverSyncScope,
  subscribeSettings,
  upsertSettingValue,
} from '@/lib/scope/store'
import type { Effective, SettingDefinition, SettingValue } from '@/lib/scope/types'
import { useCallback, useSyncExternalStore } from 'react'
import { useSettingsSnapshot } from './SettingsSnapshot'

/**
 * The snapshot React uses for the server render *and* the hydration render.
 * It is the rows the server laid out with (from the mirrored cookie), so the
 * two renders agree and a chosen layout does not reflow (BL-20260905-09).
 */
function useServerRows(): () => SettingValue[] {
  const rows = useSettingsSnapshot()
  return useCallback(() => rows, [rows])
}

/**
 * The scope id a write for ``def`` belongs on.
 *
 * A setting the user may own goes to their scope when they have one; anything
 * instance-only (a policy threshold, not a preference) always goes to the
 * instance, which is what keeps "settable at" meaningful rather than
 * decorative.
 */
export function settingWriteScope(def: SettingDefinition<unknown>): string {
  const user = userScopeFor(serverSyncScope())
  if (user && def.settableAt.includes('user')) return user.id
  return INSTANCE_SCOPE.id
}

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
    useServerRows(),
  )
  // Where a layout choice lands (BL-20260905-10). Signed in, it is the user's
  // own scope, so two people on one instance stop overwriting each other and
  // the instance value becomes the default they inherit. Signed out — and in
  // every existing test — the chain is exactly the single instance scope spec
  // 040 shipped, so nothing about the localStorage-only path changes.
  const writeScope = settingWriteScope(def)
  const chain = settingsChain(userScopeFor(serverSyncScope()))

  // The third element says where the value came from. The shell needs it to
  // tell "the user chose closed" from "nothing is stored" — a stored layout
  // choice wins over a route's default, an absent one does not.
  const effective = resolveEffective(def, chain, rows, false)
  const value = effective.value

  const set = useCallback(
    (next: T) => {
      upsertSettingValue({
        scopeId: writeScope,
        key: def.key,
        value: next,
        locked: false,
      })
    },
    [def.key, writeScope],
  )

  return [value, set, effective]
}

/**
 * Read a *list* of settings, live.
 *
 * For a menu whose rows are declared as data — a module's `layout` rows
 * (BL-20260905-07) — where the count is known only at render time. Hooks
 * cannot be called in a loop, and they do not have to be: the per-key work is
 * a pure resolve over one store snapshot, so one subscription serves every
 * key and the rows stay a plain array the caller can map over.
 */
export function useSettingList<T>(
  defs: readonly SettingDefinition<T>[],
): [T, (v: T) => void][] {
  const rows = useSyncExternalStore(
    subscribeSettings,
    listSettingValues,
    useServerRows(),
  )
  const chain = settingsChain(userScopeFor(serverSyncScope()))
  return defs.map((def) => [
    resolveEffective(def, chain, rows, false).value,
    (next: T) =>
      upsertSettingValue({
        scopeId: settingWriteScope(def as SettingDefinition<unknown>),
        key: def.key,
        value: next,
        locked: false,
      }),
  ])
}
