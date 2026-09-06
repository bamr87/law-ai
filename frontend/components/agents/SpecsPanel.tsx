'use client'

import type { SpecInfo } from '@/lib/api'
import { useMemo, useState } from 'react'
import { EmptyState, Pill, SkeletonLines, SpecStatusBadge } from './primitives'

// ---------------------------------------------------------------------------
// SpecsPanel — grouped by status with counts
// ---------------------------------------------------------------------------

export function SpecsPanel({
  specs,
  loading,
}: {
  specs: SpecInfo[]
  loading: boolean
}) {
  const [showAll, setShowAll] = useState(false)

  const grouped = useMemo(() => {
    const order = ['in-progress', 'planned', 'clarified', 'shipped', 'unknown']
    const map = new Map<string, SpecInfo[]>()
    for (const spec of specs) {
      const s = spec.status
      if (!map.has(s)) map.set(s, [])
      map.get(s)!.push(spec)
    }
    // sort by canonical order
    return [...map.entries()].sort(
      ([a], [b]) => (order.indexOf(a) ?? 99) - (order.indexOf(b) ?? 99),
    )
  }, [specs])

  const shipped = specs.filter((s) => s.status === 'shipped').length
  const inProgress = specs.filter((s) => s.status === 'in-progress').length

  if (loading) return <SkeletonLines />

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Pill tone="amber">{inProgress} in-progress</Pill>
        <Pill tone="emerald">{shipped} shipped</Pill>
        <Pill tone="slate">{specs.length} total</Pill>
      </div>
      {grouped.map(([status, items]) => (
        <div key={status} className="mb-3">
          <div className="mb-1 flex items-center gap-2">
            <SpecStatusBadge status={status} />
            <span className="text-[10px] text-slate-500">{items.length}</span>
          </div>
          <ul className="space-y-1">
            {(showAll ? items : items.slice(0, 3)).map((spec) => (
              <li
                key={spec.id}
                className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs transition hover:border-slate-700"
              >
                <span className="truncate font-mono text-slate-300">
                  {spec.id}
                </span>
              </li>
            ))}
            {!showAll && items.length > 3 && (
              <li className="text-center text-[10px] text-slate-600">
                +{items.length - 3} more
              </li>
            )}
          </ul>
        </div>
      ))}
      {specs.length > 6 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-1 text-[11px] text-slate-500 underline hover:text-slate-300"
        >
          {showAll ? 'Show less' : `Show all ${specs.length} specs`}
        </button>
      )}
      {specs.length === 0 && <EmptyState message="No specs yet." />}
    </div>
  )
}

export default SpecsPanel
