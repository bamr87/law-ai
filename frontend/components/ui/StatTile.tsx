import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { type Tone, toneWash } from './tokens'

/** KPI / metric tile with a subtle tonal wash and optional chart slot. */
export function StatTile({
  label,
  value,
  sub,
  tone = 'brand',
  chart,
  className,
}: {
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: Tone
  chart?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl border border-border bg-surface/70 p-4',
        className,
      )}
    >
      <div
        className={cn(
          'pointer-events-none absolute inset-0 bg-gradient-to-br to-transparent opacity-70',
          toneWash[tone],
        )}
      />
      <div className="relative flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-subtle">
            {label}
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums text-ink">
            {value ?? '—'}
          </div>
          {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
        </div>
        {chart && <div className="shrink-0 self-end">{chart}</div>}
      </div>
    </div>
  )
}
