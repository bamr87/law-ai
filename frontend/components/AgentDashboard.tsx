'use client'

import ProposedTestReview from '@/components/ProposedTestReview'
import {
  fetchAgentMetrics,
  fetchAgents,
  fetchBacklog,
  fetchLocalAIHealth,
  fetchLsatGaps,
  fetchRuns,
  fetchSpecs,
  type AgentInfo,
  type AgentMetric,
  type AgentRun,
  type BacklogResponse,
  type LocalAIHealth,
  type LsatGapRow,
  type SpecInfo,
} from '@/lib/api'
import { openOpsStream } from '@/lib/opsStream'
import { useUrlState, useUrlText } from '@/lib/shell/viewState'
import { useEffect, useMemo, useRef, useState } from 'react'
import AgentCard from './agents/AgentCard'
import AgentLaunchModal from './agents/AgentLaunchModal'
import { ControlBar, KPIStrip } from './agents/ControlBar'
import { FALLBACK_POLL_MS, GAP_ROWS, POLL_MS } from './agents/constants'
import HealthPanel from './agents/HealthPanel'
import MetricsPanel from './agents/MetricsPanel'
import NextAutonomyTarget from './agents/NextAutonomyTarget'
import {
  EmptyState,
  KindBadge,
  Panel,
  Pill,
  SeverityBadge,
} from './agents/primitives'
import RunDetailModal from './agents/RunDetailModal'
import { RunRow, RunTypeTabs } from './agents/RunRow'
import SpecsPanel from './agents/SpecsPanel'

/**
 * Agent operations dashboard (spec 003).
 *
 * This file is the orchestrator: it owns the polling loop, the push
 * subscription, the filters and which modal is open, and hands each panel its
 * slice of state. Every panel, row and badge lives in `./agents/`
 * (BL-20260830-02) — before that split this component was ~1,600 lines and
 * changing one panel meant scrolling past six others.
 */

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
  metrics: PanelState<{
    agents: AgentMetric[]
    window_size: number
    errors_total: number
  }>
  // BL-20260527-07: the same gap rows the nightly LSAT autonomy cycle reads,
  // so a reviewer can see tonight's target without opening the lab.
  gaps: PanelState<{ gaps: LsatGapRow[]; count: number; limit: number }>
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
    gaps: emptyState(),
  })
  const [paused, setPaused] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  // Run filters are URL state (BL-20260831-02): "the failed runs matching
  // ingest" is then a link, and Back undoes a filter instead of leaving the
  // screen. The text box replaces (debounced) so typing does not fill history;
  // the type tabs push, because picking one is a choice you can step back out
  // of.
  const [runFilter, setRunFilter] = useUrlText('q')
  const [runTypeFilter, setRunTypeFilter] = useUrlState<string>('type', {
    fallback: 'all',
  })
  const [runLimit, setRunLimit] = useState(50)
  const [, setTick] = useState(0) // forces relative-time re-render
  const seenTraceIds = useRef<Set<string>>(new Set())
  const [recentlyAdded, setRecentlyAdded] = useState<Set<string>>(new Set())
  const [launchAgent, setLaunchAgent] = useState<AgentInfo | null>(null)
  const [drillTraceId, setDrillTraceId] = useState<string | null>(null)
  // BL-20260429-16: `pushLive` says whether the ops WebSocket is connected
  // (which only slows the poll down); `pushTick` is bumped by each change
  // notification and re-runs the refresh effect immediately.
  const [pushLive, setPushLive] = useState(false)
  const [pushTick, setPushTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    const refresh = () => {
      if (cancelled) return
      void Promise.allSettled([
        load(fetchAgents, (s) => setState((prev) => ({ ...prev, agents: s }))),
        load(
          () => fetchRuns(runLimit),
          (s) => setState((prev) => ({ ...prev, runs: s })),
        ),
        load(fetchBacklog, (s) =>
          setState((prev) => ({ ...prev, backlog: s })),
        ),
        load(fetchSpecs, (s) => setState((prev) => ({ ...prev, specs: s }))),
        load(fetchLocalAIHealth, (s) =>
          setState((prev) => ({ ...prev, health: s })),
        ),
        load(
          () => fetchAgentMetrics(500),
          (s) => setState((prev) => ({ ...prev, metrics: s })),
        ),
        load(
          () => fetchLsatGaps(GAP_ROWS),
          (s) => setState((prev) => ({ ...prev, gaps: s })),
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
    const id = setInterval(refresh, pushLive ? FALLBACK_POLL_MS : POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [paused, runLimit, pushLive, pushTick])

  // Subscribe to change notifications. Nothing here fetches: the socket says
  // *something changed* and this effect re-runs the one above, so the REST
  // endpoints stay the only source of truth. jsdom has no WebSocket, so tests
  // exercise the polling fallback (BL-20260429-16).
  useEffect(() => {
    if (paused) return
    const stream = openOpsStream(() => setPushTick((t) => t + 1), {
      onStatus: setPushLive,
    })
    return () => {
      stream.close()
      setPushLive(false)
    }
  }, [paused])

  // Tick every second so relative timestamps stay fresh.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const filteredRuns = useMemo(() => {
    const runs = state.runs.data?.runs ?? []
    let result = runs
    if (runTypeFilter !== 'all') {
      result = result.filter(
        (r) => (r.type as string | undefined) === runTypeFilter,
      )
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
        pushLive={pushLive}
      />

      <KPIStrip
        agentCount={state.agents.data?.count}
        runCount={state.runs.data?.count}
        backlog={state.backlog.data?.counts}
        specCount={state.specs.data?.count}
        latencies={latencySeries}
      />

      {/* System health row */}
      <HealthPanel
        loading={state.health.loading}
        error={state.health.error}
        health={state.health.data}
      />

      {/* What tonight's LSAT autonomy cycle will draft (BL-20260527-07) */}
      <NextAutonomyTarget
        loading={state.gaps.loading}
        error={state.gaps.error}
        gaps={state.gaps.data?.gaps ?? []}
      />

      {/* What the autonomy loop drafted and is waiting on a human for
          (BL-20260511-17) */}
      <ProposedTestReview />

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
                aria-label="Filter runs"
                placeholder="Filter…"
                value={runFilter}
                onChange={(e) => setRunFilter(e.target.value)}
                className="w-28 rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:border-blue-500 focus-ring"
              />
              <select
                value={runLimit}
                onChange={(e) => setRunLimit(Number(e.target.value))}
                className="rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300 focus:border-blue-500 focus-ring"
                aria-label="Run limit"
              >
                {[25, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
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
          <ul className="shell-panel-scroll mt-2 max-h-96 space-y-1.5 pr-1">
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
              <EmptyState
                message={
                  runTypeFilter !== 'all'
                    ? `No "${runTypeFilter}" events match the filter.`
                    : `No runs match "${runFilter}".`
                }
              />
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
              {/* A scroll container with no focusable child is unreachable
               * by keyboard — axe `scrollable-region-focusable`, caught by
               * e2e/a11y.spec.ts once the list is long enough to scroll. */}
              <ul
                tabIndex={0}
                aria-label="Open backlog items"
                className="shell-panel-scroll max-h-80 space-y-1.5 pr-1 focus-ring"
              >
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
          <SpecsPanel
            specs={state.specs.data?.specs ?? []}
            loading={state.specs.loading}
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
    </div>
  )
}
