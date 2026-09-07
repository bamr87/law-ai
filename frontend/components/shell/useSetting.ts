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
import type {
  Effective,
  SettingDefinition,
  SettingValue,
} from '@/lib/scope/types'
import { useCallback, useSyncExternalStore } from 'react'
import {
  useSettingsSnapshot,
  useSettingsSnapshotScope,
} from './SettingsSnapshot'

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
 * The signed-in scope this render resolves against (BL-20260905-10).
 *
 * `serverSyncScope()` is module state set by the hydrate fetch, so it is null
 * on the server *and* through hydration — every layout row written at
 * `user:<pk>` would be skipped and the first paint would show the instance
 * default before reflowing. The mirrored scope cookie, handed down by
 * `app/(app)/layout.tsx`, fills exactly that window; once the fetch lands, the
 * live value takes over and the two agree.
 */
export function useUserScopeId(): string | null {
  const fromServerRender = useSettingsSnapshotScope()
  return serverSyncScope() ?? fromServerRender
}

/**
 * The scope id a write for ``def`` belongs on: the caller's own scope for
 * anything they may own, the instance for a policy value. This is what keeps
 * "settable at" meaningful rather than decorative.
 */
function writeScopeFor(
  def: SettingDefinition<unknown>,
  userScope: { id: string } | null,
): string {
  if (userScope && def.settableAt.includes('user')) return userScope.id
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
  const userScope = userScopeFor(useUserScopeId())
  const writeScope = writeScopeFor(def as SettingDefinition<unknown>, userScope)
  const chain = settingsChain(userScope)

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
  const userScope = userScopeFor(useUserScopeId())
  const chain = settingsChain(userScope)
  return defs.map((def) => [
    resolveEffective(def, chain, rows, false).value,
    (next: T) =>
      upsertSettingValue({
        scopeId: writeScopeFor(def as SettingDefinition<unknown>, userScope),
        key: def.key,
        value: next,
        locked: false,
      }),
  ])
}
