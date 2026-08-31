'use client'

import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { chainTo, resolveEffective } from '@/lib/scope/resolver'
import {
  deleteSettingValue,
  listSettingValues,
  upsertSettingValue,
} from '@/lib/scope/store'
import { SETTING_CATALOG } from '@/lib/settings/catalog'
import type { SettingDefinition } from '@/lib/scope/types'
import { useMemo, useState } from 'react'
import SettingField from './SettingField'

export default function SettingsForm() {
  const [rows, setRows] = useState(listSettingValues)
  const chain = useMemo(
    () => chainTo(INSTANCE_SCOPE, [INSTANCE_SCOPE]),
    [],
  )

  return (
    <div className="space-y-4">
      {SETTING_CATALOG.map((def) => (
        <CatalogField
          key={def.key}
          def={def}
          rows={rows}
          chain={chain}
          onRows={setRows}
        />
      ))}
    </div>
  )
}

function CatalogField({
  def,
  rows,
  chain,
  onRows,
}: {
  def: SettingDefinition<unknown>
  rows: ReturnType<typeof listSettingValues>
  chain: ReturnType<typeof chainTo>
  onRows: (rows: ReturnType<typeof listSettingValues>) => void
}) {
  const effective = resolveEffective(def, chain, rows, true)

  function override() {
    onRows(
      upsertSettingValue({
        scopeId: INSTANCE_SCOPE.id,
        key: def.key,
        value: effective.value,
        locked: false,
      }),
    )
  }

  function reset() {
    onRows(deleteSettingValue(INSTANCE_SCOPE.id, def.key))
  }

  function change(value: unknown) {
    onRows(
      upsertSettingValue({
        scopeId: INSTANCE_SCOPE.id,
        key: def.key,
        value,
        locked: false,
      }),
    )
  }

  return (
    <SettingField
      def={def}
      effective={effective}
      target={INSTANCE_SCOPE}
      onOverride={override}
      onReset={reset}
      onChange={change}
    />
  )
}
