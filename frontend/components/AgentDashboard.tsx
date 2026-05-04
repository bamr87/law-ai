'use client'

import {
    fetchAgents,
    fetchBacklog,
    fetchRuns,
    fetchSpecs,
    type AgentInfo,
    type AgentRun,
    type BacklogResponse,
    type SpecInfo,
} from '@/lib/api'
import { useEffect, useMemo, useRef, useState } from 'react'

const POLL_MS = 5000

interface PanelState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

const emptyState = <T,>(): PanelState<T> => ({
  data: null,
  error: null,
  loading: true,
})

interface DashboardState {
  agents: PanelState<{ agents: AgentInfo[]; count: number }>
  runs: PanelState<{ runs: AgentRun[]; count: number }>
  backlog: PanelState<BacklogResponse>
  specs: PanelState<{ specs: SpecInfo[]; count: number }>
}

async function load<T>(
  fn: () => Promise<T>,
  set: (state: PanelState<T>) => void,
) {
  try {
    const data = await fn()
    set({ data, error: null, loading: false })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'request failed'
    set({ data: null, error: message, loading: false })
  }
}

export default function AgentDashboard() {
  const [state, setState] = useState<DashboardState>({
    agents: emptyState(),
    runs: emptyState(),
    backlog: emptyState(),
    specs: emptyState(),
  })
  const [paused, setPaused] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [runFilter, setRunFilter] = useState('')
  const [, setTick] = useState(0) // forces relative-time re-render
  const seenTraceIds = useRef<Set<string>>(new Set())
  const [recentlyAdded, setRecentlyAdded] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    const refresh = () => {
      if (cancelled) return
      void Promise.allSettled([
        load(fetchAgents, (s) =>
          setState((prev) => ({ ...prev, agents: s })),
        ),
        load(() => fetchRuns(50), (s) =>
          setState((prev) => ({ ...prev, runs: s })),
        ),
        load(fetchBacklog, (s) =>
          setState((prev) => ({ ...prev, backlog: s })),
        ),
        load(fetchSpecs, (s) =>
          setState((prev) => ({ ...prev, specs: s })),
        ),
      ]).then(() => {
        if (!cancelled) setLastUpdated(new Date())
      })
    }
    refresh()
    if (paused) {
      return () => {
        cancelled = true
      }
    }
    const id = setInterval(refresh, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [paused])

  // Tick every second so relative timestamps stay fresh.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const filteredRuns = useMemo(() => {
    const runs = state.runs.data?.runs ?? []
    if (!runFilter) return runs
    const q = runFilter.toLowerCase()
    return runs.filter((r) => JSON.stringify(r).toLowerCase().includes(q))
  }, [state.runs.data, runFilter])

  // Detect newly arrived runs by trace_id and flash them briefly.
  useEffect(() => {
    const runs = state.runs.data?.runs ?? []
    if (runs.length === 0) return
    const fresh: string[] = []
    for (const r of runs) {
      const id = (r.trace_id as string | undefined) ?? ''
      if (id && !seenTraceIds.current.has(id)) {
        seenTraceIds.current.add(id)
        fresh.push(id)
      }
    }
    // Skip the initial bulk-load flash.
    if (fresh.length > 0 && seenTraceIds.current.size > fresh.length) {
      setRecentlyAdded((prev) => new Set([...prev, ...fresh]))
      const timer = setTimeout(() => {
        setRecentlyAdded((prev) => {
          const next = new Set(prev)
          for (const id of fresh) next.delete(id)
          return next
        })
      }, 2500)
      return () => clearTimeout(timer)
    }
  }, [state.runs.data])

  // Latency series for the sparkline (oldest → newest).
  const latencySeries = useMemo(() => {
    const runs = state.runs.data?.runs ?? []
    return runs
      .map((r) => Number(r.latency_ms))
      .filter((n) => Number.isFinite(n) && n >= 0)
      .slice(0, 40)
      .reverse()
  }, [state.runs.data])

  return (
    <div className="space-y-6">
      <ControlBar
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        lastUpdated={lastUpdated}
      />

      <KPIStrip
        agentCount={state.agents.data?.count}
        runCount={state.runs.data?.count}
        backlog={state.backlog.data?.counts}
        specCount={state.specs.data?.count}
        latencies={latencySeries}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel
          title="Registry"
          subtitle="Agents currently registered with the backend"
          loading={state.agents.loading}
          error={state.agents.error}
        >
          <ul className="space-y-2" data-testid="registry-list">
            {state.agents.data?.agents.map((agent) => (
              <li
                key={agent.name}
                className="group rounded-lg border border-slate-800 bg-slate-900/40 p-3 transition hover:border-blue-500/40 hover:bg-slate-900/80"
                data-testid="registry-card"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
                    <span className="font-medium text-slate-100">
                      {agent.name}
                    </span>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider text-slate-500">
                    ready
                  </span>
                </div>
                <div className="mt-1 truncate font-mono text-xs text-slate-500">
                  {agent.module}
                </div>
              </li>
            ))}
            {state.agents.data?.count === 0 && (
              <EmptyState message="No agents registered." />
            )}
          </ul>
        </Panel>

        <Panel
          title="Recent Runs"
          subtitle="Streaming from /api/agents/runs"
          loading={state.runs.loading}
          error={state.runs.error}
          actions={
            <input
              type="text"
              placeholder="Filter…"
              value={runFilter}
              onChange={(e) => setRunFilter(e.target.value)}
              className="w-32 rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          }
        >
          <ul className="max-h-96 space-y-1.5 overflow-auto pr-1">
            {filteredRuns.map((run, i) => {
              const id = (run.trace_id as string | undefined) ?? `${i}`
              return (
                <RunRow
                  key={id}
                  run={run}
                  fresh={recentlyAdded.has(id)}
                />
              )
            })}
            {filteredRuns.length === 0 && (state.runs.data?.count ?? 0) > 0 && (
              <EmptyState message={`No runs match "${runFilter}".`} />
            )}
            {state.runs.data?.count === 0 && (
              <EmptyState message="No runs recorded yet." />
            )}
          </ul>
        </Panel>

        <Panel
          title="Backlog"
          subtitle="BL-* items tracked in BACKLOG.md"
          loading={state.backlog.loading}
          error={state.backlog.error}
        >
          {state.backlog.data && (
            <>
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                <Pill tone="blue">Open: {state.backlog.data.counts.open}</Pill>
                <Pill tone="amber">
                  Claimed: {state.backlog.data.counts.claimed}
                </Pill>
                <Pill tone="emerald">
                  Done: {state.backlog.data.counts.done}
                </Pill>
                <Pill tone="slate">
                  Total: {state.backlog.data.counts.total}
                </Pill>
              </div>
              <ul className="max-h-80 space-y-1.5 overflow-auto pr-1">
                {state.backlog.data.open.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-md border border-slate-800 bg-slate-900/40 p-2 text-sm"
                  >
                    <div className="flex items-start gap-2">
                      <SeverityBadge severity={item.severity} />
                      <KindBadge kind={item.kind} />
                      <span className="font-mono text-[10px] text-slate-500">
                        {item.id}
                      </span>
                    </div>
                    <div className="mt-1 text-sm text-slate-300">
                      {item.title}
                    </div>
                  </li>
                ))}
                {state.backlog.data.open.length === 0 && (
                  <EmptyState message="No open items 🎉" />
                )}
              </ul>
            </>
          )}
        </Panel>

        <Panel
          title="Specs"
          subtitle="Spec lifecycle from specs/"
          loading={state.specs.loading}
          error={state.specs.error}
        >
          <ul className="space-y-2">
            {state.specs.data?.specs.map((spec) => (
              <li
                key={spec.id}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-sm transition hover:border-slate-700"
              >
                <span className="truncate font-mono text-xs text-slate-300">
                  {spec.id}
                </span>
                <SpecStatusBadge status={spec.status} />
              </li>
            ))}
            {state.specs.data?.count === 0 && (
              <EmptyState message="No specs yet." />
            )}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ControlBar({
  paused,
  onTogglePause,
  lastUpdated,
}: {
  paused: boolean
  onTogglePause: () => void
  lastUpdated: Date | null
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-2.5">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span
          className={
            'inline-block h-2 w-2 rounded-full ' +
            (paused ? 'bg-amber-400' : 'animate-pulse bg-emerald-400')
          }
        />
        {paused ? 'Polling paused' : `Auto-refresh every ${POLL_MS / 1000}s`}
        {lastUpdated && (
          <span className="text-slate-500">
            · last updated {relativeTime(lastUpdated)}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onTogglePause}
        className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 transition hover:border-blue-500/50 hover:text-white"
      >
        {paused ? '▶ Resume' : '⏸ Pause'}
      </button>
    </div>
  )
}

function KPIStrip({
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

function Sparkline({
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

function KPI({
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

function Panel({
  title,
  subtitle,
  loading,
  error,
  actions,
  children,
}: {
  title: string
  subtitle?: string
  loading: boolean
  error: string | null
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 shadow-sm backdrop-blur">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-100">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
          )}
        </div>
        {actions}
      </header>
      {loading && <SkeletonLines />}
      {error && (
        <p
          className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300"
          role="alert"
        >
          Failed to load: {error}
        </p>
      )}
      {!loading && !error && children}
    </section>
  )
}

function SkeletonLines() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-8 animate-pulse rounded-md bg-slate-800/60"
          style={{ animationDelay: `${i * 100}ms` }}
        />
      ))}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <li className="rounded-md border border-dashed border-slate-800 p-3 text-center text-xs text-slate-500">
      {message}
    </li>
  )
}

function RunRow({ run, fresh }: { run: AgentRun; fresh?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const label =
    (run.agent as string | undefined) ??
    (run.type as string | undefined) ??
    'event'
  const time = run.timestamp ? new Date(run.timestamp as string) : null
  const traceId = run.trace_id as string | undefined
  return (
    <li
      className={
        'rounded-md border bg-slate-900/30 p-2 text-xs transition ' +
        (fresh
          ? 'border-emerald-500/40 ring-1 ring-inset ring-emerald-500/20'
          : 'border-slate-800 hover:border-slate-700')
      }
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={expanded ? 'Hide run details' : 'Show run details'}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <div className="flex min-w-0 items-center gap-2">
          <span
            aria-hidden
            className={
              'inline-block w-3 text-center text-slate-500 transition ' +
              (expanded ? 'rotate-90' : '')
            }
          >
            ▸
          </span>
          <TypeIcon type={String(run.type ?? '')} />
          <span className="truncate font-mono text-slate-200">{label}</span>
          {fresh && (
            <span className="shrink-0 rounded-full bg-emerald-500/20 px-1.5 text-[9px] uppercase tracking-wider text-emerald-300">
              new
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-slate-500">
          {run.latency_ms != null && (
            <span className="rounded bg-slate-800 px-1.5 py-0.5 tabular-nums">
              {Math.round(Number(run.latency_ms))} ms
            </span>
          )}
          {time && <span title={time.toISOString()}>{relativeTime(time)}</span>}
        </div>
      </button>
      {(run.path || run.method) && (
        <div className="mt-1 truncate pl-5 font-mono text-[10px] text-slate-500">
          {String(run.method ?? '')} {String(run.path ?? '')}
        </div>
      )}
      {expanded && (
        <div className="mt-2 space-y-2 border-t border-slate-800 pt-2 pl-5">
          {traceId && (
            <div className="text-[10px] text-slate-500">
              trace_id{' '}
              <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
                {traceId}
              </code>
            </div>
          )}
          <pre className="max-h-60 overflow-auto rounded bg-slate-950/80 p-2 font-mono text-[10px] leading-relaxed text-slate-300">
            {JSON.stringify(run, null, 2)}
          </pre>
        </div>
      )}
    </li>
  )
}

function TypeIcon({ type }: { type: string }) {
  const map: Record<string, { color: string; glyph: string }> = {
    http_request: { color: 'bg-sky-500/20 text-sky-300', glyph: '↦' },
    agent_call: { color: 'bg-violet-500/20 text-violet-300', glyph: '⚙' },
    graph_query: { color: 'bg-emerald-500/20 text-emerald-300', glyph: '◆' },
  }
  const { color, glyph } = map[type] ?? {
    color: 'bg-slate-700 text-slate-300',
    glyph: '·',
  }
  return (
    <span
      className={
        'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs ' +
        color
      }
      title={type || 'event'}
    >
      {glyph}
    </span>
  )
}

function Pill({
  children,
  tone,
}: {
  children: React.ReactNode
  tone: 'blue' | 'amber' | 'emerald' | 'slate' | 'red'
}) {
  const tones: Record<string, string> = {
    blue: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    slate: 'bg-slate-700/40 text-slate-300 border-slate-600/40',
    red: 'bg-red-500/15 text-red-300 border-red-500/30',
  }
  return (
    <span
      className={
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ' +
        tones[tone]
      }
    >
      {children}
    </span>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const tone: 'red' | 'amber' | 'slate' =
    severity === 'high' ? 'red' : severity === 'med' ? 'amber' : 'slate'
  return <Pill tone={tone}>{severity}</Pill>
}

function KindBadge({ kind }: { kind: string }) {
  return <Pill tone="slate">{kind}</Pill>
}

function SpecStatusBadge({ status }: { status: string }) {
  const tone: 'blue' | 'amber' | 'emerald' | 'slate' =
    status === 'shipped'
      ? 'emerald'
      : status === 'in-progress'
        ? 'amber'
        : status === 'planned' || status === 'clarified'
          ? 'blue'
          : 'slate'
  return <Pill tone={tone}>{status}</Pill>
}

function relativeTime(d: Date): string {
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
