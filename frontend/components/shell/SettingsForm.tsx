'use client'

import {
  INSTANCE_SCOPE,
  settingsChain,
  userScopeFor,
} from '@/lib/scope/instance'
import { resolveEffective } from '@/lib/scope/resolver'
import {
  deleteSettingValue,
  getSettingsServerSnapshot,
  listSettingValues,
  serverSyncScope,
  subscribeSettings,
  upsertSettingValue,
} from '@/lib/scope/store'
import { SETTING_CATALOG } from '@/lib/settings/catalog'
import type { ScopeNode, SettingDefinition, SettingValue } from '@/lib/scope/types'
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
/**
 * Section headings by key prefix. The catalog is ordered so a prefix's
 * settings are contiguous; a prefix not named here still gets a heading,
 * spelled from the key, so a new family is never silently unlabelled.
 */
const GROUP_LABEL: Record<string, string> = {
  analysis: 'Analysis',
  graph: 'Knowledge graph',
  ui: 'Layout',
  lsat: 'LSAT Lab',
}

function groupOf(key: string): string {
  return key.split('.')[0]
}

export default function SettingsForm() {
  const rows = useSyncExternalStore(
    subscribeSettings,
    listSettingValues,
    getSettingsServerSnapshot,
  )
  // BL-20260905-10: a signed-in caller edits their *own* rows for anything
  // settable at user scope, and sees the instance value as the inherited
  // default behind it. Signed out, this is the single instance scope spec 040
  // shipped and every field behaves exactly as before.
  const userScope = userScopeFor(serverSyncScope())
  const chain = useMemo(() => settingsChain(userScope), [userScope])

  const groups = useMemo(() => {
    const out: { id: string; label: string; defs: SettingDefinition<unknown>[] }[] = []
    for (const def of SETTING_CATALOG) {
      const id = groupOf(def.key)
      const last = out[out.length - 1]
      if (last && last.id === id) last.defs.push(def)
      else out.push({ id, label: GROUP_LABEL[id] ?? id, defs: [def] })
    }
    return out
  }, [])

  return (
    <div className="space-y-8">
      {groups.map((group) => (
        <section key={group.id} aria-labelledby={`settings-${group.id}`}>
          <h2
            id={`settings-${group.id}`}
            className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
          >
            {group.label}
          </h2>
          <div className="space-y-4">
            {group.defs.map((def) => (
              <CatalogField key={def.key} def={def} rows={rows} chain={chain} />
            ))}
          </div>
        </section>
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
  chain: ScopeNode[]
}) {
  const effective = resolveEffective(def, chain, rows, true)
  // The deepest scope in the chain that may hold this setting: a layout
  // preference lands on the user, a policy value stays on the instance even
  // for a signed-in editor.
  const target =
    [...chain].reverse().find((node) => def.settableAt.includes(node.type)) ??
    INSTANCE_SCOPE

  return (
    <SettingField
      def={def}
      effective={effective}
      target={target}
      onOverride={() =>
        upsertSettingValue({
          scopeId: target.id,
          key: def.key,
          value: effective.value,
          locked: false,
        })
      }
      onReset={() => deleteSettingValue(target.id, def.key)}
      onChange={(value) =>
        upsertSettingValue({
          scopeId: target.id,
          key: def.key,
          value,
          locked: false,
        })
      }
    />
  )
}
