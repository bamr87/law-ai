'use client'

import type { Effective, ScopeNode, SettingDefinition } from '@/lib/scope/types'
import InheritanceBadge from './InheritanceBadge'

export default function SettingField<T>({
  def,
  effective,
  target,
  onOverride,
  onReset,
  onChange,
}: {
  def: SettingDefinition<T>
  effective: Effective<T>
  target: ScopeNode
  onOverride: () => void
  onReset: () => void
  onChange: (value: T) => void
}) {
  const locked = effective.locked
  const controlDisabled =
    locked || effective.isInherited || effective.source === 'default'

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{def.label}</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">{def.help}</p>
        </div>
        <Control
          def={def}
          value={effective.value}
          disabled={controlDisabled}
          onChange={onChange}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <InheritanceBadge effective={effective} />
        {effective.canOverride &&
          (effective.isInherited || effective.source === 'default') && (
            <button
              type="button"
              onClick={onOverride}
              className="rounded-md border border-slate-700 px-2 py-0.5 text-[11px] text-slate-200 hover:border-blue-500/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
            >
              Override for {target.name}
            </button>
          )}
        {effective.canOverride &&
          !effective.isInherited &&
          effective.source !== 'default' && (
            <button
              type="button"
              onClick={onReset}
              className="rounded-md border border-slate-700 px-2 py-0.5 text-[11px] text-slate-200 hover:border-blue-500/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
            >
              Reset to inherited
            </button>
          )}
      </div>
      {controlDisabled && !locked ? (
        <p className="sr-only">This control is inherited. Use Override to edit.</p>
      ) : null}
    </div>
  )
}

function Control<T>({
  def,
  value,
  disabled,
  onChange,
}: {
  def: SettingDefinition<T>
  value: T
  disabled: boolean
  onChange: (value: T) => void
}) {
  if (typeof def.default === 'boolean') {
    const on = Boolean(value)
    return (
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={def.label}
        disabled={disabled}
        onClick={() => onChange((!on) as T)}
        className={
          'relative h-6 w-10 shrink-0 rounded-full transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 disabled:cursor-not-allowed disabled:opacity-50 ' +
          (on ? 'bg-blue-600' : 'bg-slate-700')
        }
      >
        <span
          className={
            'absolute top-0.5 h-5 w-5 rounded-full bg-white transition ' +
            (on ? 'left-4' : 'left-0.5')
          }
        />
      </button>
    )
  }
  if (typeof def.default === 'number') {
    return (
      <input
        type="number"
        step="0.05"
        min={0}
        max={1}
        aria-label={def.label}
        disabled={disabled}
        value={value as number}
        onChange={(e) => {
          const n = Number(e.target.value)
          if (Number.isFinite(n)) onChange(n as T)
        }}
        className="w-20 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
      />
    )
  }
  return (
    <span className="text-xs text-slate-500">{String(value)}</span>
  )
}
