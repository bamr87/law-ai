'use client'

import { cn } from '@/lib/cn'
import { useAgents, useBacklog, useSpecs } from '@/lib/queries'
import { useHydrated } from '@/lib/useHydrated'
import { type Tone, toneDot } from '@/components/ui'

/** Compact live status strip on the landing page — driven by the shared
 *  React Query hooks instead of a bespoke 3-endpoint poller. */
export default function HomeStats() {
  const hydrated = useHydrated()
  const agents = useAgents()
  const backlog = useBacklog()
  const specs = useSpecs()

  // Gate live values behind hydration so the first client render matches SSR.
  const online = hydrated && agents.isSuccess
  const offline = hydrated && agents.isError
  const shipped = specs.data?.specs.filter((s) => s.status === 'shipped').length

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/60 p-1 backdrop-blur">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-border/60 sm:grid-cols-4">
        <Stat
          label="Backend"
          value={online ? 'Online' : offline ? 'Offline' : '…'}
          tone={online ? 'success' : offline ? 'danger' : 'brand'}
          pulse={online}
        />
        <Stat
          label="Agents"
          value={hydrated ? (agents.data?.count ?? '—') : '…'}
          tone="brand"
        />
        <Stat
          label="Backlog"
          value={hydrated ? (backlog.data?.counts.open ?? '—') : '…'}
          sub={
            hydrated && backlog.data
              ? `${backlog.data.counts.done} shipped`
              : undefined
          }
          tone="warning"
        />
        <Stat
          label="Specs"
          value={hydrated ? (specs.data?.count ?? '—') : '…'}
          sub={
            hydrated && shipped != null ? `${shipped} shipped` : undefined
          }
          tone="accent"
        />
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  sub,
  tone,
  pulse,
}: {
  label: string
  value: number | string
  sub?: string
  tone: Tone
  pulse?: boolean
}) {
  return (
    <div className="bg-canvas-soft/70 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-subtle">
        <span
          className={cn(
            'inline-block h-1.5 w-1.5 rounded-full',
            toneDot[tone],
            pulse && 'animate-pulse',
          )}
        />
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">
        {value}
      </div>
      {sub && <div className="text-xs text-subtle">{sub}</div>}
    </div>
  )
}
