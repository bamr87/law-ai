'use client'

import { fetchAgents, fetchBacklog, fetchSpecs } from '@/lib/api'
import { useEffect, useState } from 'react'

interface Stats {
  agents: number | null
  backlogOpen: number | null
  backlogDone: number | null
  specsTotal: number | null
  specsShipped: number | null
  online: boolean
}

const initial: Stats = {
  agents: null,
  backlogOpen: null,
  backlogDone: null,
  specsTotal: null,
  specsShipped: null,
  online: false,
}

export default function HomeStats() {
  const [stats, setStats] = useState<Stats>(initial)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [a, b, s] = await Promise.all([
          fetchAgents(),
          fetchBacklog(),
          fetchSpecs(),
        ])
        if (cancelled) return
        setStats({
          agents: a.count,
          backlogOpen: b.counts.open,
          backlogDone: b.counts.done,
          specsTotal: s.count,
          specsShipped: s.specs.filter((x) => x.status === 'shipped').length,
          online: true,
        })
      } catch {
        if (!cancelled) setStats({ ...initial, online: false })
      }
    }
    void load()
    const id = setInterval(load, 10_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 p-1 backdrop-blur">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-slate-800/40 sm:grid-cols-4">
        <Stat label="Backend" value={stats.online ? 'Online' : 'Offline'} accent={stats.online ? 'emerald' : 'red'} pulse={stats.online} />
        <Stat label="Agents" value={stats.agents ?? '—'} accent="blue" />
        <Stat
          label="Backlog"
          value={stats.backlogOpen ?? '—'}
          sub={stats.backlogDone != null ? `${stats.backlogDone} shipped` : undefined}
          accent="amber"
        />
        <Stat
          label="Specs"
          value={stats.specsTotal ?? '—'}
          sub={
            stats.specsShipped != null
              ? `${stats.specsShipped} shipped`
              : undefined
          }
          accent="indigo"
        />
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  sub,
  accent,
  pulse,
}: {
  label: string
  value: number | string
  sub?: string
  accent: 'emerald' | 'blue' | 'amber' | 'indigo' | 'red'
  pulse?: boolean
}) {
  const dot: Record<string, string> = {
    emerald: 'bg-emerald-400',
    blue: 'bg-blue-400',
    amber: 'bg-amber-400',
    indigo: 'bg-indigo-400',
    red: 'bg-red-400',
  }
  return (
    <div className="bg-slate-950/60 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span
          className={
            'inline-block h-1.5 w-1.5 rounded-full ' +
            dot[accent] +
            // BL-20260831-03: a "live" dot is decoration, so it stops for
            // anyone who asked the OS for reduced motion.
            (pulse ? ' animate-pulse motion-reduce:animate-none' : '')
          }
        />
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">
        {value}
      </div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  )
}
