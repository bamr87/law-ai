'use client'

import {
    fetchAgentMetrics,
    fetchAgents,
    fetchAutonomy,
    fetchBacklog,
    fetchLocalAIHealth,
    fetchRunDetail,
    fetchRuns,
    fetchSessionDetail,
    fetchSessions,
    fetchSpecs,
    runAnalysis,
    type AgentInfo,
    type AgentMetric,
    type AgentRun,
    type AutonomyState,
    type BacklogResponse,
    type LocalAIHealth,
    type SessionRun,
    type SpecInfo,
} from '@/lib/api'
import {
    useAgentActivity,
    type ActivityEvent,
} from '@/lib/useAgentActivity'
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
  health: PanelState<LocalAIHealth>
  metrics: PanelState<{ agents: AgentMetric[]; window_size: number; errors_total: number }>
  autonomy: PanelState<AutonomyState>
  sessions: PanelState<{ sessions: SessionRun[]; count: number }>
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
    health: emptyState(),
    metrics: emptyState(),
    autonomy: emptyState(),
    sessions: emptyState(),
  })
  const [paused, setPaused] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [runFilter, setRunFilter] = useState('')
  const [runTypeFilter, setRunTypeFilter] = useState<string>('all')
  const [runLimit, setRunLimit] = useState(50)
  const [, setTick] = useState(0) // forces relative-time re-render
  const seenTraceIds = useRef<Set<string>>(new Set())
  const [recentlyAdded, setRecentlyAdded] = useState<Set<string>>(new Set())
  const [launchAgent, setLaunchAgent] = useState<AgentInfo | null>(null)
  const [drillTraceId, setDrillTraceId] = useState<string | null>(null)
  const [drillSessionId, setDrillSessionId] = useState<string | null>(null)

  // Live activity feed (WS3) — a real-time layer over the 5s poll. When the
  // socket is down, `connected` is false and polling remains the source of truth.
  const activity = useAgentActivity({ max: 30 })

  useEffect(() => {
    let cancelled = false
    const refresh = () => {
      if (cancelled) return
      void Promise.allSettled([
        load(fetchAgents, (s) =>
          setState((prev) => ({ ...prev, agents: s })),
        ),
        load(() => fetchRuns(runLimit), (s) =>
          setState((prev) => ({ ...prev, runs: s })),
        ),
        load(fetchBacklog, (s) =>
          setState((prev) => ({ ...prev, backlog: s })),
        ),
        load(fetchSpecs, (s) =>
          setState((prev) => ({ ...prev, specs: s })),
        ),
        load(fetchLocalAIHealth, (s) =>
          setState((prev) => ({ ...prev, health: s })),
        ),
        load(() => fetchAgentMetrics(500), (s) =>
          setState((prev) => ({ ...prev, metrics: s })),
        ),
        load(fetchAutonomy, (s) =>
          setState((prev) => ({ ...prev, autonomy: s })),
        ),
        load(() => fetchSessions({ limit: 25 }), (s) =>
          setState((prev) => ({ ...prev, sessions: s })),
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
  }, [paused, runLimit])

  // Tick every second so relative timestamps stay fresh.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // A live event means a new audit row landed — refresh the runs + metrics
  // panels immediately rather than waiting for the next poll tick. Skipped
  // while paused. `activity.lastEventAt` only changes on a real frame.
  useEffect(() => {
    if (paused || activity.lastEventAt == null) return
    void load(() => fetchRuns(runLimit), (s) =>
      setState((prev) => ({ ...prev, runs: s })),
    )
    void load(() => fetchAgentMetrics(500), (s) =>
      setState((prev) => ({ ...prev, metrics: s })),
    )
  }, [activity.lastEventAt, paused, runLimit])

  const filteredRuns = useMemo(() => {
    const runs = state.runs.data?.runs ?? []
    let result = runs
    if (runTypeFilter !== 'all') {
      result = result.filter((r) => (r.type as string | undefined) === runTypeFilter)
    }
    if (!runFilter) return result
    const q = runFilter.toLowerCase()
    return result.filter((r) => JSON.stringify(r).toLowerCase().includes(q))
  }, [state.runs.data, runFilter, runTypeFilter])

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
        live={activity.connected}
      />

      <LiveActivityStrip
        connected={activity.connected}
        events={activity.events}
      />

      <KPIStrip
        agentCount={state.agents.data?.count}
        runCount={state.runs.data?.count}
        backlog={state.backlog.data?.counts}
        specCount={state.specs.data?.count}
        latencies={latencySeries}
      />

      {/* Autonomy mission-control row */}
      <AutonomyPanel
        loading={state.autonomy.loading}
        error={state.autonomy.error}
        data={state.autonomy.data}
      />

      {/* System health row */}
      <HealthPanel
        loading={state.health.loading}
        error={state.health.error}
        health={state.health.data}
      />

      {/* Per-agent metrics */}
      <MetricsPanel
        loading={state.metrics.loading}
        error={state.metrics.error}
        data={state.metrics.data}
        onSelectTrace={setDrillTraceId}
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
              <AgentCard
                key={agent.name}
                agent={agent}
                onLaunch={() => setLaunchAgent(agent)}
              />
            ))}
            {state.agents.data?.count === 0 && (
              <EmptyState message="No agents registered." />
            )}
          </ul>
        </Panel>

        <Panel
          title="Recent Runs"
          subtitle={`Showing ${filteredRuns.length} of ${state.runs.data?.count ?? '…'} events`}
          loading={state.runs.loading}
          error={state.runs.error}
          actions={
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Filter…"
                value={runFilter}
                onChange={(e) => setRunFilter(e.target.value)}
                className="w-28 rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
              />
              <select
                value={runLimit}
                onChange={(e) => setRunLimit(Number(e.target.value))}
                className="rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300 focus:border-blue-500 focus:outline-none"
                aria-label="Run limit"
              >
                {[25, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          }
        >
          <RunTypeTabs
            runs={state.runs.data?.runs ?? []}
            active={runTypeFilter}
            onChange={setRunTypeFilter}
          />
          <ul className="mt-2 max-h-96 space-y-1.5 overflow-auto pr-1">
            {filteredRuns.map((run, i) => {
              const id = (run.trace_id as string | undefined) ?? `${i}`
              return (
                <RunRow
                  key={id}
                  run={run}
                  fresh={recentlyAdded.has(id)}
                  onDrill={(tid) => setDrillTraceId(tid)}
                />
              )
            })}
            {filteredRuns.length === 0 && (state.runs.data?.count ?? 0) > 0 && (
              <EmptyState message={runTypeFilter !== 'all'
                ? `No "${runTypeFilter}" events match the filter.`
                : `No runs match "${runFilter}".`
              } />
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
          <SpecsPanel specs={state.specs.data?.specs ?? []} loading={state.specs.loading} />
        </Panel>

        <Panel
          title="Sessions"
          subtitle="Change ledger — every agent work-session (newest first)"
          loading={state.sessions.loading}
          error={state.sessions.error}
        >
          <SessionsList
            sessions={state.sessions.data?.sessions ?? []}
            onDrill={setDrillSessionId}
          />
        </Panel>
      </div>

      {/* Agent launch modal */}
      {launchAgent && (
        <AgentLaunchModal
          agent={launchAgent}
          onClose={() => setLaunchAgent(null)}
          onTrace={(tid) => {
            setLaunchAgent(null)
            setDrillTraceId(tid)
          }}
        />
      )}

      {/* Run detail drill-in */}
      {drillTraceId && (
        <RunDetailModal
          traceId={drillTraceId}
          onClose={() => setDrillTraceId(null)}
        />
      )}

      {/* Session drill-in (change-ledger timeline) */}
      {drillSessionId && (
        <SessionDetailModal
          sessionId={drillSessionId}
          onClose={() => setDrillSessionId(null)}
          onTrace={(tid) => {
            setDrillSessionId(null)
            setDrillTraceId(tid)
          }}
        />
      )}
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
  live,
}: {
  paused: boolean
  onTogglePause: () => void
  lastUpdated: Date | null
  live: boolean
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
      <div className="flex items-center gap-2">
        <span
          data-testid="live-badge"
          title={
            live
              ? 'Live WebSocket feed connected'
              : 'WebSocket offline — falling back to polling'
          }
          className={
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ' +
            (live
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-slate-700 bg-slate-800/40 text-slate-500')
          }
        >
          <span
            className={
              'inline-block h-1.5 w-1.5 rounded-full ' +
              (live ? 'animate-pulse bg-emerald-400' : 'bg-slate-500')
            }
          />
          {live ? 'Live' : 'Polling'}
        </span>
        <button
          type="button"
          onClick={onTogglePause}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300 transition hover:border-blue-500/50 hover:text-white"
        >
          {paused ? '▶ Resume' : '⏸ Pause'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LiveActivityStrip — real-time ticker of streamed provenance frames (WS3)
// ---------------------------------------------------------------------------

function LiveActivityStrip({
  connected,
  events,
}: {
  connected: boolean
  events: ActivityEvent[]
}) {
  // Hidden until there's something live to show — keeps the chrome quiet when
  // the socket is unavailable and the dashboard is poll-only.
  if (!connected && events.length === 0) return null
  return (
    <div
      className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-2"
      data-testid="live-activity-strip"
    >
      <span className="flex shrink-0 items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-emerald-300">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        Live
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
        {events.length === 0 ? (
          <span className="text-[11px] text-slate-500">
            Connected — waiting for activity…
          </span>
        ) : (
          events.slice(0, 12).map((ev, i) => <ActivityChip key={i} event={ev} />)
        )}
      </div>
    </div>
  )
}

function ActivityChip({ event }: { event: ActivityEvent }) {
  const label = event.agent ?? event.cycle_type ?? event.type
  const isError = event.status === 'error' || event.status === 'failed'
  const time = event.timestamp ? new Date(event.timestamp) : null
  return (
    <span
      className={
        'inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] ' +
        (isError
          ? 'border-red-500/40 bg-red-500/10 text-red-300'
          : 'border-slate-700 bg-slate-800/40 text-slate-300')
      }
      title={time ? time.toISOString() : event.type}
    >
      <TypeIcon type={event.type} />
      <span className="max-w-[140px] truncate font-mono">{label}</span>
      {event.latency_ms != null && (
        <span className="tabular-nums text-slate-500">
          {Math.round(Number(event.latency_ms))}ms
        </span>
      )}
    </span>
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

function RunRow({
  run,
  fresh,
  onDrill,
}: {
  run: AgentRun
  fresh?: boolean
  onDrill?: (traceId: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const label =
    (run.agent as string | undefined) ??
    (run.type as string | undefined) ??
    'event'
  const time = run.timestamp ? new Date(run.timestamp as string) : null
  const traceId = run.trace_id as string | undefined
  const inputObj = (run as Record<string, unknown>).input as Record<string, unknown> | undefined
  const isError = inputObj?.error === true || (run as Record<string, unknown>).error === true
  return (
    <li
      className={
        'rounded-md border bg-slate-900/30 p-2 text-xs transition ' +
        (isError
          ? 'border-red-500/40 ring-1 ring-inset ring-red-500/20'
          : fresh
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
          {isError && (
            <span className="shrink-0 rounded-full bg-red-500/20 px-1.5 text-[9px] uppercase tracking-wider text-red-300">
              error
            </span>
          )}
          {fresh && !isError && (
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
            <div className="flex items-center gap-2 text-[10px] text-slate-500">
              <span>trace_id</span>
              <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
                {traceId}
              </code>
              {onDrill && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDrill(traceId) }}
                  className="rounded border border-blue-600/40 bg-blue-600/10 px-2 py-0.5 text-[10px] text-blue-300 transition hover:border-blue-500 hover:bg-blue-600/20"
                >
                  View all related events →
                </button>
              )}
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

// ---------------------------------------------------------------------------
// AgentCard — enhanced registry card with launch button
// ---------------------------------------------------------------------------

const AGENT_DESCRIPTIONS: Record<string, string> = {
  LegalAnalyst: 'IRAC-style analysis of legal issues with precedent retrieval.',
  PrecedentHunter: 'Searches the knowledge graph for relevant case precedents.',
  IngestionScout: 'Discovers and queues new legal opinions from public sources.',
  StatuteScout: 'Discovers and queues statutes/ordinances from public sources.',
  LSATContentAuthor: 'Drafts LSAT practice questions for human (HITL) review.',
}

function AgentCard({
  agent,
  onLaunch,
}: {
  agent: AgentInfo
  onLaunch: () => void
}) {
  const desc = AGENT_DESCRIPTIONS[agent.name] ?? 'Agent ready.'
  return (
    <li
      className="group rounded-lg border border-slate-800 bg-slate-900/40 p-3 transition hover:border-blue-500/40 hover:bg-slate-900/80"
      data-testid="registry-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
          <span className="font-medium text-slate-100">{agent.name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            ready
          </span>
          {(agent.name === 'LegalAnalyst' || agent.name === 'PrecedentHunter') && (
            <button
              type="button"
              onClick={onLaunch}
              className="rounded border border-blue-600/40 bg-blue-600/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-blue-300 transition hover:border-blue-500 hover:bg-blue-600/20"
            >
              Run
            </button>
          )}
        </div>
      </div>
      <div className="mt-1 text-xs text-slate-400">{desc}</div>
      <div className="mt-1 truncate font-mono text-[10px] text-slate-600">
        {agent.module}
      </div>
    </li>
  )
}

// ---------------------------------------------------------------------------
// HealthPanel — local AI system health overview
// ---------------------------------------------------------------------------

function HealthPanel({
  loading,
  error,
  health,
}: {
  loading: boolean
  error: string | null
  health: LocalAIHealth | null
}) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <SkeletonLines />
      </div>
    )
  }
  if (error) return null // silently skip — health probe can fail without alarming users

  if (!health) return null

  const services: Array<{ label: string; reachable: boolean; detail: string }> = [
    {
      label: 'Ollama',
      reachable: health.ollama.reachable,
      detail: health.ollama.reachable
        ? `${health.ollama.models.length} model${health.ollama.models.length !== 1 ? 's' : ''}: ${health.ollama.models.slice(0, 3).join(', ')}${health.ollama.models.length > 3 ? '…' : ''}`
        : (health.ollama.error ?? 'unreachable'),
    },
    {
      label: `LangGraph (${health.checkpointer.kind})`,
      reachable: health.checkpointer.reachable,
      detail: health.checkpointer.reachable
        ? 'Checkpointer connected'
        : (health.checkpointer.error ?? 'unreachable'),
    },
    {
      label: 'Phoenix Tracing',
      reachable: health.phoenix.reachable,
      detail: health.phoenix.enabled
        ? health.phoenix.reachable
          ? health.phoenix.ui_url
          : (health.phoenix.error ?? 'unreachable')
        : 'disabled',
    },
  ]

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
      <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
        System Health
      </div>
      <div className="flex flex-wrap gap-3">
        {services.map(({ label, reachable, detail }) => (
          <div
            key={label}
            className={
              'flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ' +
              (reachable
                ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300'
                : 'border-red-500/30 bg-red-500/5 text-red-300')
            }
          >
            <span
              className={
                'inline-block h-1.5 w-1.5 shrink-0 rounded-full ' +
                (reachable ? 'bg-emerald-400' : 'bg-red-400')
              }
            />
            <span className="font-medium">{label}</span>
            <span className="max-w-[200px] truncate text-[10px] opacity-60">
              {detail}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunTypeTabs — filter runs by event type
// ---------------------------------------------------------------------------

const RUN_TYPES = ['all', 'http_request', 'agent_call', 'graph_query'] as const

function RunTypeTabs({
  runs,
  active,
  onChange,
}: {
  runs: AgentRun[]
  active: string
  onChange: (t: string) => void
}) {
  const counts = useMemo(() => {
    const map: Record<string, number> = { all: runs.length }
    for (const r of runs) {
      const t = String(r.type ?? 'other')
      map[t] = (map[t] ?? 0) + 1
    }
    return map
  }, [runs])

  return (
    <div className="flex gap-1 overflow-x-auto pb-1">
      {RUN_TYPES.map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onChange(t)}
          className={
            'shrink-0 rounded-md px-2.5 py-1 text-[11px] font-medium transition ' +
            (active === t
              ? 'bg-blue-600/20 text-blue-300 ring-1 ring-inset ring-blue-500/40'
              : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300')
          }
        >
          {t === 'all' ? 'All' : t.replace('_', ' ')}
          {counts[t] !== undefined && (
            <span className="ml-1 opacity-60">{counts[t]}</span>
          )}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SpecsPanel — grouped by status with counts
// ---------------------------------------------------------------------------

function SpecsPanel({ specs, loading }: { specs: SpecInfo[]; loading: boolean }) {
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
                <span className="truncate font-mono text-slate-300">{spec.id}</span>
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

// ---------------------------------------------------------------------------
// AgentLaunchModal — run LegalAnalyst or PrecedentHunter
// ---------------------------------------------------------------------------

function AgentLaunchModal({
  agent,
  onClose,
  onTrace,
}: {
  agent: AgentInfo
  onClose: () => void
  onTrace?: (traceId: string) => void
}) {
  const [text, setText] = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [useLangGraph, setUseLangGraph] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [resultTrace, setResultTrace] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    setLoading(true)
    setResult(null)
    setResultTrace(null)
    setError(null)
    try {
      const resp = await runAnalysis({
        text: text.trim(),
        jurisdiction: jurisdiction.trim() || undefined,
        use_langgraph: useLangGraph,
      })
      // Capture trace_id from first agent (LegalAnalyst) so the user can drill in
      const firstTrace = resp.agent_trace.find((t) => t.trace_id)?.trace_id ?? null
      setResultTrace(firstTrace)
      const irac = resp.irac
      setResult(
        [
          `Mode: ${useLangGraph ? 'LangGraph (real Ollama)' : 'legacy stub'}`,
          `Issue: ${irac.issue}`,
          `Rule: ${irac.rule}`,
          `Application: ${irac.application}`,
          `Conclusion: ${irac.conclusion}`,
          `Confidence: ${(resp.confidence * 100).toFixed(0)}%`,
          resp.requires_human_review ? '⚠ Requires human review (HITL)' : '',
          resp.irac.sources.length > 0
            ? `Sources: ${resp.irac.sources.map((s) => s.title ?? s.url ?? '').filter(Boolean).join(', ')}`
            : '',
        ]
          .filter(Boolean)
          .join('\n\n'),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={`Run ${agent.name}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-100">Run {agent.name}</h2>
            <p className="mt-0.5 text-xs text-slate-500">{AGENT_DESCRIPTIONS[agent.name]}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-500 hover:text-slate-200"
          >
            ✕
          </button>
        </header>

        <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-3 p-5">
          <div>
            <label htmlFor="agent-input-text" className="mb-1 block text-xs font-medium text-slate-400">
              Legal Issue / Case Text
            </label>
            <textarea
              id="agent-input-text"
              rows={4}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Describe the legal issue or paste a case fact pattern…"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
              required
            />
          </div>
          <div>
            <label htmlFor="agent-jurisdiction" className="mb-1 block text-xs font-medium text-slate-400">
              Jurisdiction (optional)
            </label>
            <input
              id="agent-jurisdiction"
              type="text"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              placeholder="e.g. Colorado, 10th Circuit"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <label className="flex items-start gap-2 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs">
            <input
              type="checkbox"
              checked={useLangGraph}
              onChange={(e) => setUseLangGraph(e.target.checked)}
              className="mt-0.5 accent-blue-500"
            />
            <span className="flex-1 text-slate-300">
              <span className="font-medium">Real mode (LangGraph + Ollama)</span>
              <span className="block text-[11px] text-slate-500">
                When off, returns a canned IRAC for fast UI testing (legacy stub).
                When on, invokes the real LegalWorkflow against Ollama and Neo4j.
              </span>
            </span>
          </label>

          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
              {error}
            </p>
          )}

          {result && (
            <>
              <pre className="max-h-52 overflow-auto rounded-md border border-slate-800 bg-slate-950/80 p-3 text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap">
                {result}
              </pre>
              {resultTrace && onTrace && (
                <button
                  type="button"
                  onClick={() => onTrace(resultTrace)}
                  className="w-full rounded-md border border-blue-600/40 bg-blue-600/10 px-3 py-2 text-xs text-blue-300 transition hover:border-blue-500 hover:bg-blue-600/20"
                >
                  View provenance trace ({resultTrace.slice(0, 8)}…) →
                </button>
              )}
            </>
          )}

          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-700 px-4 py-2 text-xs text-slate-400 hover:text-slate-200"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={loading || !text.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-xs font-medium text-white transition hover:bg-blue-500 disabled:opacity-50"
            >
              {loading ? 'Running…' : 'Run Analysis'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MetricsPanel — per-agent aggregated metrics from /api/agents/metrics
// ---------------------------------------------------------------------------

function MetricsPanel({
  loading,
  error,
  data,
  onSelectTrace,
}: {
  loading: boolean
  error: string | null
  data: { agents: AgentMetric[]; window_size: number; errors_total: number } | null
  onSelectTrace: (traceId: string) => void
}) {
  if (loading) return null
  if (error || !data) return null
  if (data.agents.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
          Per-Agent Metrics
        </div>
        <div className="mt-2 text-xs text-slate-500">
          No agent calls in the last {data.window_size} events. Run an agent to populate.
        </div>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
          Per-Agent Metrics
        </div>
        <div className="text-[10px] text-slate-500">
          Window: last {data.window_size} events
          {data.errors_total > 0 && (
            <span className="ml-2 text-red-400">· {data.errors_total} error{data.errors_total !== 1 ? 's' : ''}</span>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800 text-left text-[10px] uppercase tracking-wider text-slate-500">
              <th className="py-2 pr-3 font-medium">Agent</th>
              <th className="py-2 pr-3 font-medium">Calls</th>
              <th className="py-2 pr-3 font-medium">Success</th>
              <th className="py-2 pr-3 font-medium">p50</th>
              <th className="py-2 pr-3 font-medium">p95</th>
              <th className="py-2 pr-3 font-medium">Avg Conf</th>
              <th className="py-2 pr-3 font-medium">Last Seen</th>
              <th className="py-2 pr-3 font-medium">Last Trace</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((m) => (
              <tr key={m.agent} className="border-b border-slate-800/40 last:border-0">
                <td className="py-2 pr-3 font-mono text-slate-200">{m.agent}</td>
                <td className="py-2 pr-3 tabular-nums text-slate-300">
                  {m.count}
                  {m.error_count > 0 && (
                    <span className="ml-1 text-red-400">({m.error_count} err)</span>
                  )}
                </td>
                <td className="py-2 pr-3 tabular-nums">
                  <span
                    className={
                      m.success_rate != null && m.success_rate < 0.9
                        ? 'text-red-300'
                        : 'text-emerald-300'
                    }
                  >
                    {m.success_rate != null ? `${(m.success_rate * 100).toFixed(0)}%` : '—'}
                  </span>
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.latency_p50_ms != null ? `${m.latency_p50_ms}ms` : '—'}
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.latency_p95_ms != null ? `${m.latency_p95_ms}ms` : '—'}
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.avg_confidence != null ? `${(m.avg_confidence * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="py-2 pr-3 text-slate-500">
                  {m.last_seen ? relativeTime(new Date(m.last_seen)) : '—'}
                </td>
                <td className="py-2 pr-3">
                  {m.last_trace_id ? (
                    <button
                      type="button"
                      onClick={() => onSelectTrace(m.last_trace_id!)}
                      className="font-mono text-[10px] text-blue-300 underline hover:text-blue-200"
                    >
                      {m.last_trace_id.slice(0, 8)}…
                    </button>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AutonomyPanel — kill-switch state + recent autonomous-cycle activity (WS3)
// ---------------------------------------------------------------------------

function cycleTone(status: string | null): 'emerald' | 'red' | 'slate' {
  return status === 'ok'
    ? 'emerald'
    : status === 'error'
      ? 'red'
      : 'slate'
}

function AutonomyPanel({
  loading,
  error,
  data,
}: {
  loading: boolean
  error: string | null
  data: AutonomyState | null
}) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <SkeletonLines />
      </div>
    )
  }
  if (error || !data) return null
  const { enabled, last_cycle, recent_cycles, recent_violations, allowed_sources } =
    data
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
          Autonomy
        </div>
        <span
          className={
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ' +
            (enabled
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
              : 'border-amber-500/40 bg-amber-500/10 text-amber-300')
          }
        >
          <span
            className={
              'inline-block h-1.5 w-1.5 rounded-full ' +
              (enabled ? 'animate-pulse bg-emerald-400' : 'bg-amber-400')
            }
          />
          {enabled ? 'ENABLED' : 'kill-switch OFF'}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {last_cycle ? (
          <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
            <span className="text-slate-500">Last cycle</span>
            <span className="font-mono text-slate-200">
              {last_cycle.cycle_type ?? 'cycle'}
            </span>
            <Pill tone={cycleTone(last_cycle.status)}>
              {last_cycle.status ?? '—'}
            </Pill>
            {last_cycle.duration_ms != null && (
              <span className="tabular-nums text-slate-500">
                {Math.round(last_cycle.duration_ms)} ms
              </span>
            )}
            <span className="text-slate-500">
              {relativeTime(new Date(last_cycle.completed_at))}
            </span>
          </div>
        ) : (
          <span className="text-slate-500">No autonomy cycles recorded yet.</span>
        )}
        {allowed_sources.length > 0 && (
          <span className="text-[10px] text-slate-500">
            sources: {allowed_sources.join(', ')}
          </span>
        )}
        {recent_violations.length > 0 && (
          <Pill tone="red">
            {recent_violations.length} policy violation
            {recent_violations.length !== 1 ? 's' : ''}
          </Pill>
        )}
      </div>
      {recent_cycles.length > 1 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-slate-600">recent:</span>
          {recent_cycles.slice(0, 16).map((c, i) => (
            <span
              key={c.cycle_id ?? i}
              title={`${c.cycle_type ?? 'cycle'} · ${c.status ?? '—'} · ${c.completed_at}`}
              className={
                'inline-block h-2 w-2 rounded-full ' +
                (c.status === 'ok'
                  ? 'bg-emerald-400/80'
                  : c.status === 'error'
                    ? 'bg-red-400/80'
                    : 'bg-slate-600')
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SessionsList — the change ledger (WS4): one row per agent work-session
// ---------------------------------------------------------------------------

function SourceBadge({ source }: { source: string }) {
  const tones: Record<string, string> = {
    claude_code: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
    copilot: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    celery: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
    human: 'bg-slate-700/40 text-slate-300 border-slate-600/40',
  }
  const tone = tones[source] ?? 'bg-slate-700/40 text-slate-300 border-slate-600/40'
  return (
    <span
      className={
        'inline-flex shrink-0 items-center rounded border px-1.5 text-[9px] uppercase tracking-wider ' +
        tone
      }
    >
      {source}
    </span>
  )
}

function sessionStatusTone(status: string): 'emerald' | 'amber' | 'red' | 'slate' {
  if (status === 'completed') return 'emerald'
  if (status === 'running') return 'amber'
  if (status === 'failed' || status === 'blocked') return 'red'
  return 'slate'
}

function SessionsList({
  sessions,
  onDrill,
}: {
  sessions: SessionRun[]
  onDrill: (sessionId: string) => void
}) {
  if (sessions.length === 0) {
    return (
      <ul>
        <EmptyState message="No agent sessions recorded yet." />
      </ul>
    )
  }
  return (
    <ul className="max-h-96 space-y-1.5 overflow-auto pr-1">
      {sessions.map((s) => (
        <li
          key={s.session_id}
          className="rounded-md border border-slate-800 bg-slate-900/30 p-2 text-xs transition hover:border-slate-700"
        >
          <button
            type="button"
            onClick={() => onDrill(s.session_id)}
            className="flex w-full items-center justify-between gap-2 text-left"
            aria-label={`Open session ${s.session_id}`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <Pill tone={sessionStatusTone(s.status)}>{s.status}</Pill>
              <SourceBadge source={s.agent_source} />
              <span className="truncate font-mono text-slate-200">
                {s.kind || s.agent_name || s.session_id.slice(0, 8)}
              </span>
            </div>
            <div className="flex shrink-0 items-center gap-2 text-[11px] text-slate-500">
              {s.backlog_items_added.length > 0 && (
                <span title="backlog items added">
                  +{s.backlog_items_added.length} BL
                </span>
              )}
              {s.prs_created.length > 0 && (
                <span title="PRs created">{s.prs_created.length} PR</span>
              )}
              {s.started_at && <span>{relativeTime(new Date(s.started_at))}</span>}
            </div>
          </button>
          {s.spec_claimed && (
            <div className="mt-1 truncate pl-1 font-mono text-[10px] text-slate-500">
              spec: {s.spec_claimed}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// SessionDetailModal — one session + its full provenance timeline (WS4)
// ---------------------------------------------------------------------------

function SessionDetailModal({
  sessionId,
  onClose,
  onTrace,
}: {
  sessionId: string
  onClose: () => void
  onTrace?: (traceId: string) => void
}) {
  const [session, setSession] = useState<SessionRun | null>(null)
  const [events, setEvents] = useState<AgentRun[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchSessionDetail(sessionId)
      .then((data) => {
        if (!cancelled) {
          setSession(data.session)
          setEvents(data.events)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'fetch failed')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Session details"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-3xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-100">Session</h2>
            <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
              {sessionId}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-500 hover:text-slate-200"
          >
            ✕
          </button>
        </header>

        <div className="max-h-[70vh] overflow-auto p-5">
          {loading && <SkeletonLines />}
          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </p>
          )}
          {!loading && !error && session && (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
              <Pill tone={sessionStatusTone(session.status)}>{session.status}</Pill>
              <SourceBadge source={session.agent_source} />
              {session.kind && (
                <span className="font-mono text-slate-300">{session.kind}</span>
              )}
              {session.spec_claimed && (
                <span className="font-mono text-[10px] text-slate-500">
                  {session.spec_claimed}
                </span>
              )}
              {session.backlog_items_added.map((bl) => (
                <Pill key={bl} tone="blue">
                  {bl}
                </Pill>
              ))}
            </div>
          )}
          {!loading && !error && session?.summary && (
            <pre className="mb-4 max-h-32 overflow-auto whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950/60 p-3 text-[11px] leading-relaxed text-slate-300">
              {session.summary}
            </pre>
          )}
          {events && events.length === 0 && (
            <p className="text-sm text-slate-400">
              No audit events linked to this session yet.
            </p>
          )}
          {events && events.length > 0 && (
            <>
              <div className="mb-2 text-xs text-slate-400">
                {events.length} event{events.length !== 1 ? 's' : ''} in this session
              </div>
              <ol className="space-y-2">
                {events.map((ev, i) => {
                  const traceId = ev.trace_id as string | undefined
                  return (
                    <li
                      key={i}
                      className="rounded-md border border-slate-800 bg-slate-950/40 p-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <TypeIcon type={String(ev.type ?? '')} />
                          <span className="truncate font-mono text-slate-200">
                            {String(ev.agent ?? ev.type ?? 'event')}
                          </span>
                          {ev.model != null && (
                            <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                              {String(ev.model)}
                            </span>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-2 text-[10px] text-slate-500">
                          {ev.latency_ms != null && (
                            <span>{Math.round(Number(ev.latency_ms))} ms</span>
                          )}
                          {ev.timestamp != null && (
                            <span>{relativeTime(new Date(String(ev.timestamp)))}</span>
                          )}
                          {traceId && onTrace && (
                            <button
                              type="button"
                              onClick={() => onTrace(traceId)}
                              className="rounded border border-blue-600/40 bg-blue-600/10 px-1.5 text-blue-300 hover:border-blue-500"
                            >
                              trace →
                            </button>
                          )}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunDetailModal — fetches all events for one trace_id
// ---------------------------------------------------------------------------

function RunDetailModal({
  traceId,
  onClose,
}: {
  traceId: string
  onClose: () => void
}) {
  const [events, setEvents] = useState<AgentRun[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchRunDetail(traceId)
      .then((data) => {
        if (!cancelled) {
          setEvents(data.events)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'fetch failed')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [traceId])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Run details"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-3xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-100">Provenance Trace</h2>
            <p className="mt-0.5 font-mono text-[11px] text-slate-500">{traceId}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-500 hover:text-slate-200"
          >
            ✕
          </button>
        </header>

        <div className="max-h-[70vh] overflow-auto p-5">
          {loading && <SkeletonLines />}
          {error && (
            <p className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </p>
          )}
          {events && events.length === 0 && (
            <p className="text-sm text-slate-400">
              No events found for this trace_id. The audit log may have rotated.
            </p>
          )}
          {events && events.length > 0 && (
            <>
              <div className="mb-3 text-xs text-slate-400">
                {events.length} event{events.length !== 1 ? 's' : ''} share this trace
              </div>
              <ol className="space-y-3">
                {events.map((ev, i) => {
                  const inp = (ev as Record<string, unknown>).input as Record<string, unknown> | undefined
                  const isError = inp?.error === true
                  return (
                    <li
                      key={i}
                      className={
                        'rounded-md border p-3 text-xs ' +
                        (isError
                          ? 'border-red-500/40 bg-red-500/5'
                          : 'border-slate-800 bg-slate-950/40')
                      }
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <TypeIcon type={String(ev.type ?? '')} />
                          <span className="font-mono font-medium text-slate-200">
                            {String(ev.agent ?? ev.type ?? 'event')}
                          </span>
                          {ev.model && (
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                              {String(ev.model)}
                            </span>
                          )}
                          {isError && (
                            <span className="rounded-full bg-red-500/20 px-2 text-[10px] uppercase text-red-300">
                              error
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500">
                          {ev.latency_ms != null && (
                            <span>{Math.round(Number(ev.latency_ms))} ms</span>
                          )}
                          {ev.confidence != null && (
                            <span>conf {(Number(ev.confidence) * 100).toFixed(0)}%</span>
                          )}
                          {ev.timestamp && (
                            <span>{relativeTime(new Date(String(ev.timestamp)))}</span>
                          )}
                        </div>
                      </div>
                      <pre className="max-h-48 overflow-auto rounded bg-slate-950/80 p-2 font-mono text-[10px] leading-relaxed text-slate-300">
                        {JSON.stringify(ev, null, 2)}
                      </pre>
                    </li>
                  )
                })}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
