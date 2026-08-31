'use client'

import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { chainTo, resolveEffective } from '@/lib/scope/resolver'
import {
  deleteSettingValue,
  getSettingsServerSnapshot,
  listSettingValues,
  subscribeSettings,
  upsertSettingValue,
} from '@/lib/scope/store'
import { SETTING_CATALOG } from '@/lib/settings/catalog'
import type { SettingDefinition, SettingValue } from '@/lib/scope/types'
import { useMemo, useSyncExternalStore } from 'react'
import SettingField from './SettingField'

/**
 * `useSyncExternalStore`, not `useState(listSettingValues)`.
 *
 * The store is localStorage-backed, so reading it for the initial render made
 * the server (which sees nothing) and the client (which sees the saved rows)
 * disagree — a hydration mismatch that only appeared once a setting actually
 * had a stored value. `useSyncExternalStore` renders the server snapshot
 * through hydration and swaps afterwards, and subscribing means a preference
 * changed elsewhere on the page (the LSAT timer's own "Move" menu) shows up
 * here without a reload.
 */
export default function SettingsForm() {
  const rows = useSyncExternalStore(
    subscribeSettings,
    listSettingValues,
    getSettingsServerSnapshot,
  )
  const chain = useMemo(() => chainTo(INSTANCE_SCOPE, [INSTANCE_SCOPE]), [])

  return (
    <div className="space-y-4">
      {SETTING_CATALOG.map((def) => (
        <CatalogField key={def.key} def={def} rows={rows} chain={chain} />
      ))}
    </div>
  )
}

function CatalogField({
  def,
  rows,
  chain,
}: {
  def: SettingDefinition<unknown>
  rows: SettingValue[]
  chain: ReturnType<typeof chainTo>
}) {
  const effective = resolveEffective(def, chain, rows, true)

  return (
    <SettingField
      def={def}
      effective={effective}
      target={INSTANCE_SCOPE}
      onOverride={() =>
        upsertSettingValue({
          scopeId: INSTANCE_SCOPE.id,
          key: def.key,
          value: effective.value,
          locked: false,
        })
      }
      onReset={() => deleteSettingValue(INSTANCE_SCOPE.id, def.key)}
      onChange={(value) =>
        upsertSettingValue({
          scopeId: INSTANCE_SCOPE.id,
          key: def.key,
          value,
          locked: false,
        })
      }
    />
  )
}
