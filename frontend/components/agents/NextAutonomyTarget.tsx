'use client'

import type { LsatGapRow } from '@/lib/api'
import Link from 'next/link'
import { Pill, SkeletonLines } from './primitives'

// ---------------------------------------------------------------------------
// NextAutonomyTarget — what tonight's LSAT content cycle will draft
// ---------------------------------------------------------------------------

/**
 * `run_autonomy`'s LSAT content kind calls `proposals_store.gap_analysis(limit=1)`
 * and drafts for whatever comes back first. The lab's Authoring tab shows the
 * same table, but a reviewer watching agent ops should not have to change
 * screens to answer "what is it going to write tonight?" (BL-20260527-07).
 */
export function NextAutonomyTarget({
  loading,
  error,
  gaps,
}: {
  loading: boolean
  error: string | null
  gaps: LsatGapRow[]
}) {
  // A gap probe that fails is not an ops emergency; the health row above
  // already reports a backend that is genuinely down.
  if (error) return null
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <SkeletonLines />
      </div>
    )
  }

  const [top, ...rest] = gaps

  return (
    <section
      aria-labelledby="next-autonomy-target-heading"
      data-testid="next-autonomy-target"
      className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="next-autonomy-target-heading"
          className="text-xs font-medium uppercase tracking-wider text-slate-500"
        >
          Next autonomy target
        </h2>
        <Link
          href="/lsat?tab=authoring"
          className="rounded text-[11px] text-blue-400 hover:text-blue-300 focus-ring"
        >
          Open LSAT authoring →
        </Link>
      </div>
      {!top ? (
        <p className="mt-2 text-xs text-slate-500">
          No measured gaps yet — the next cycle has nothing to target.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-slate-500">
            Tonight&apos;s LSAT content cycle drafts for the top row.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <Pill tone="amber">{top.section}</Pill>
            <span className="font-medium text-slate-200">{top.concept}</span>
            <span className="text-xs text-slate-500">
              {top.attempts} attempt{top.attempts === 1 ? '' : 's'} ·{' '}
              {Math.round(top.accuracy * 100)}% accuracy
            </span>
          </div>
          {rest.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer rounded text-[11px] text-slate-500 hover:text-slate-300 focus-ring">
                {rest.length} more measured gap{rest.length === 1 ? '' : 's'}
              </summary>
              <ul className="mt-1 space-y-1 text-xs text-slate-400">
                {rest.map((g, i) => (
                  <li key={`${g.section}-${g.concept}-${i}`}>
                    <span className="font-mono text-[10px] text-slate-500">
                      {g.section}
                    </span>{' '}
                    {g.concept} — {g.attempts} attempt
                    {g.attempts === 1 ? '' : 's'} ·{' '}
                    {Math.round(g.accuracy * 100)}%
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  )
}

export default NextAutonomyTarget
