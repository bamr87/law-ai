import type { Effective } from '@/lib/scope/types'

export default function InheritanceBadge<T>({
  effective,
}: {
  effective: Effective<T>
}) {
  if (effective.source === 'default') {
    return (
      <p className="text-xs text-slate-500">
        Using definition default
        {effective.canOverride ? ' · Override for this instance' : ''}
      </p>
    )
  }
  if (effective.locked && effective.lockedBy) {
    return (
      <p className="text-xs text-amber-200/90">
        Locked by {effective.lockedBy.scopeName}. Contact an operator to change.
      </p>
    )
  }
  if (effective.isInherited) {
    return (
      <p className="text-xs text-slate-500">
        Inherited from {effective.source.scopeName}
        {effective.canOverride ? ' · Override for this instance' : ''}
      </p>
    )
  }
  return (
    <p className="text-xs text-slate-500">
      Set on {effective.source.scopeName}
      {effective.canOverride ? ' · Reset to inherited' : ''}
    </p>
  )
}
