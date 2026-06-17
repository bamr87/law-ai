import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface StatItem {
  label: ReactNode
  value: ReactNode
  hint?: ReactNode
}

/**
 * EDGAR `.meta-stat-grid` — a responsive auto-fill grid of centered
 * value/label tiles, used as the summary-stats block at the top of a page.
 */
export function StatGrid({
  items,
  min = 130,
  className,
}: {
  items: StatItem[]
  min?: number
  className?: string
}) {
  return (
    <div
      className={cn('grid gap-2.5', className)}
      style={{
        gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))`,
      }}
    >
      {items.map((s, i) => (
        <div
          key={i}
          className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-center"
        >
          <span className="block text-xl font-bold tabular-nums text-ink">
            {s.value ?? '—'}
          </span>
          <span className="text-[0.72rem] uppercase tracking-wide text-muted">
            {s.label}
          </span>
          {s.hint && <span className="mt-0.5 block text-[11px] text-subtle">{s.hint}</span>}
        </div>
      ))}
    </div>
  )
}
