/**
 * The small presentational pieces the LSAT Lab panels share: header stats,
 * the difficulty badge, loading skeletons, and the retryable error banner.
 *
 * Phase 1 of the Lab split (BL-20260830-02) moved these out of `LsatLab.tsx`
 * verbatim. They are still one-off Tailwind class strings; swapping them onto
 * `frontend/ui` primitives is the phase that waits on spec 039.
 *
 * static-parity: none — the static export styles the same roles with its own
 * plain-CSS `.pill` / `.btn` / `.empty` classes (spec 039 NFR-PERF-1 keeps it
 * Tailwind-free), so there is no component to share, only a look to keep close.
 */

import type { LsatDifficulty } from '@/lib/api'

export function Stat({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className="font-mono text-sm tabular-nums text-slate-100">
        {value}
        {sub && <span className="ml-1.5 text-xs text-slate-500">({sub})</span>}
      </div>
    </div>
  )
}

export function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-300">{value}</dd>
    </div>
  )
}

export function DiffBadge({ difficulty }: { difficulty: LsatDifficulty }) {
  const styles: Record<LsatDifficulty, string> = {
    intro: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
    easy: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
    med: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
    hard: 'bg-red-500/15 text-red-300 ring-red-500/30',
    elite: 'bg-fuchsia-500/15 text-fuchsia-300 ring-fuchsia-500/30',
  }
  const label =
    difficulty === 'med'
      ? 'Medium'
      : difficulty[0].toUpperCase() + difficulty.slice(1)
  return (
    <span
      className={
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ' +
        styles[difficulty]
      }
    >
      {label}
    </span>
  )
}

export function SkeletonQuestion() {
  return (
    <div className="animate-pulse space-y-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
      <div className="h-3 w-32 rounded bg-slate-800" />
      <div className="h-5 w-full rounded bg-slate-800" />
      <div className="h-5 w-5/6 rounded bg-slate-800" />
      <div className="h-5 w-2/3 rounded bg-slate-800" />
      <div className="space-y-2 pt-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 w-full rounded-lg bg-slate-800/60" />
        ))}
      </div>
    </div>
  )
}

export function SkeletonGrid() {
  return (
    <div className="grid animate-pulse gap-3 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-40 rounded-2xl border border-slate-800 bg-slate-900/40"
        />
      ))}
    </div>
  )
}

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
    >
      {message}
      {onRetry && (
        <button
          onClick={onRetry}
          className="ml-3 underline hover:text-red-200"
        >
          Retry
        </button>
      )}
    </div>
  )
}
