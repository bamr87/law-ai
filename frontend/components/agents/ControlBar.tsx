'use client'

import { StickyToolbar } from '@/components/shell/PageLayout'
import type { BacklogResponse } from '@/lib/api'
import { POLL_MS } from './constants'
import { relativeTime } from './primitives'

/** The dashboard's header strip: live/paused control and the KPI row. */

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

export function ControlBar({
  paused,
  onTogglePause,
  lastUpdated,
  pushLive,
}: {
  paused: boolean
  onTogglePause: () => void
  lastUpdated: Date | null
  pushLive: boolean
}) {
  // Pinned under the page header: "is this live and when did it last update"
  // is the question an operator re-asks constantly while reading the run
  // trail, and the pause control has to be reachable without scrolling back.
  return (
    <StickyToolbar label="Polling controls">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span
            className={
              'inline-block h-2 w-2 rounded-full ' +
              (paused
                ? 'bg-amber-400'
                : 'animate-pulse bg-emerald-400 motion-reduce:animate-none')
            }
          />
          {paused
            ? 'Polling paused'
            : pushLive
              ? 'Live — updates pushed as they happen'
              : `Auto-refresh every ${POLL_MS / 1000}s`}
          {lastUpdated && (
            <span className="text-slate-500">
              · last updated {relativeTime(lastUpdated)}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onTogglePause}
          aria-pressed={paused}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 transition hover:border-blue-500/50 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
        >
          {paused ? '▶ Resume' : '⏸ Pause'}
        </button>
      </div>
    </StickyToolbar>
  )
}

export function KPIStrip({
  agentCount,
  runCount,
  backlog,
  specCount,
  latencies,
}: {
  agentCount?: number
  runCount?: number
  backlog?: BacklogResponse['counts']
  specCount?: number
  latencies: number[]
}) {
  const avg =
    latencies.length > 0
      ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
      : null
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <KPI label="Agents" value={agentCount} accent="blue" />
      <KPI
        label="Audit Events"
        value={runCount}
        sub={avg != null ? `avg ${avg} ms` : undefined}
        accent="indigo"
        chart={<Sparkline values={latencies} stroke="#a5b4fc" />}
      />
      <KPI
        label="Open Backlog"
        value={backlog?.open}
        sub={backlog ? `${backlog.done} shipped` : undefined}
        accent="amber"
      />
      <KPI label="Active Specs" value={specCount} accent="emerald" />
    </div>
  )
}

export function Sparkline({
  values,
  stroke,
  width = 80,
  height = 24,
}: {
  values: number[]
  stroke: string
  width?: number
  height?: number
}) {
  if (values.length < 2) return null
  const max = Math.max(...values, 1)
  const min = Math.min(...values)
  const range = Math.max(max - min, 1)
  const step = width / (values.length - 1)
  const pts = values
    .map((v, i) => {
      const x = i * step
      const y = height - ((v - min) / range) * (height - 2) - 1
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const last = values[values.length - 1]
  const lx = (values.length - 1) * step
  const ly = height - ((last - min) / range) * (height - 2) - 1
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="opacity-90"
      aria-label={`Sparkline of recent latencies (last value ${Math.round(last)} ms)`}
      role="img"
    >
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pts}
      />
      <circle cx={lx} cy={ly} r={1.8} fill={stroke} />
    </svg>
  )
}

export function KPI({
  label,
  value,
  sub,
  accent,
  chart,
}: {
  label: string
  value: number | undefined
  sub?: string
  accent: 'blue' | 'indigo' | 'amber' | 'emerald'
  chart?: React.ReactNode
}) {
  const accentMap: Record<string, string> = {
    blue: 'from-blue-500/20 to-blue-500/0',
    indigo: 'from-indigo-500/20 to-indigo-500/0',
    amber: 'from-amber-500/20 to-amber-500/0',
    emerald: 'from-emerald-500/20 to-emerald-500/0',
  }
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div
        className={
          'pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60 ' +
          accentMap[accent]
        }
      />
      <div className="relative flex items-start justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">
            {label}
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums text-slate-100">
            {value ?? '—'}
          </div>
          {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
        </div>
        {chart && <div className="shrink-0 self-end">{chart}</div>}
      </div>
    </div>
  )
}
