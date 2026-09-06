'use client'

import {
  INSTANCE_SCOPE,
  settingsChain,
  userScopeFor,
} from '@/lib/scope/instance'
import { resolveEffective, writeTargetIn } from '@/lib/scope/resolver'
import {
  deleteSettingValue,
  getSettingsServerSnapshot,
  listSettingValues,
  mayWriteScope,
  subscribeSettings,
  upsertSettingValue,
} from '@/lib/scope/store'
import { useUserScopeId } from './useSetting'
import { SETTING_CATALOG } from '@/lib/settings/catalog'
import type {
  ScopeNode,
  SettingDefinition,
  SettingValue,
} from '@/lib/scope/types'
import { useMemo, useState, useSyncExternalStore } from 'react'
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
  const userScope = userScopeFor(useUserScopeId())
  // …and the other half of that move: an admin still has to be able to seed
  // the instance default everyone inherits. Targeting the deepest settable
  // scope and nothing else left no UI able to write an instance row at all,
  // so which scope you are editing is a choice, not an inference. (The server
  // still decides: an instance write from a non-admin is refused there, and
  // the row stays local to this browser exactly as it did before accounts.)
  const [editing, setEditing] = useState<'user' | 'instance'>('user')
  // BL-20260906-73: the server refuses an instance write from a non-admin and
  // the row silently stays local to this browser. `GET /api/settings/values`
  // now says which scopes the caller may write, so the option can be honest
  // about it instead of the help text hedging with "admins only". Unknown
  // (nothing hydrated, or an older backend) stays optimistic.
  const mayWriteInstance = mayWriteScope(INSTANCE_SCOPE.id)
  const effectiveEditing =
    editing === 'instance' && !mayWriteInstance ? 'user' : editing
  const chain = useMemo(
    () =>
      userScope && effectiveEditing === 'user'
        ? settingsChain(userScope)
        : [INSTANCE_SCOPE],
    [userScope, effectiveEditing],
  )

  const groups = useMemo(() => {
    const out: {
      id: string
      label: string
      defs: SettingDefinition<unknown>[]
    }[] = []
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
      {userScope && (
        <ScopeChoice
          editing={effectiveEditing}
          onChange={setEditing}
          mayWriteInstance={mayWriteInstance}
        />
      )}
      {groups.map((group) => (
        <section key={group.id} aria-labelledby={`settings-${group.id}`}>
          <h2
            id={`settings-${group.id}`}
            className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400"
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
  // for a signed-in editor. Same rule the resolver reads `canOverride` from,
  // so the button that appears and the row it writes cannot disagree.
  const target = writeTargetIn(def, chain) ?? INSTANCE_SCOPE

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

/**
 * Which scope this form edits (BL-20260905-10).
 *
 * Only shown to a signed-in caller, because signing out leaves exactly one
 * scope and a chooser with one option is noise.
 */
function ScopeChoice({
  editing,
  onChange,
  mayWriteInstance,
}: {
  editing: 'user' | 'instance'
  onChange: (next: 'user' | 'instance') => void
  mayWriteInstance: boolean
}) {
  return (
    <fieldset className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <legend className="px-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        Editing
      </legend>
      <div className="flex flex-wrap gap-4">
        {(
          [
            ['user', 'Your preferences', 'Yours alone on this instance.'],
            [
              'instance',
              'Instance defaults',
              mayWriteInstance
                ? 'What everyone here inherits.'
                : 'What everyone here inherits. Your account cannot set it.',
            ],
          ] as const
        ).map(([value, label, help]) => {
          const disabled = value === 'instance' && !mayWriteInstance
          return (
            <label
              key={value}
              className={
                'flex items-start gap-2 text-xs ' +
                (disabled ? 'text-slate-500' : 'text-slate-300')
              }
            >
              <input
                type="radio"
                name="settings-scope"
                value={value}
                checked={editing === value}
                disabled={disabled}
                onChange={() => onChange(value)}
                className="mt-0.5"
              />
              <span>
                <span
                  className={
                    'font-medium ' +
                    (disabled ? 'text-slate-400' : 'text-slate-100')
                  }
                >
                  {label}
                </span>
                <span className="block text-slate-400">{help}</span>
              </span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
