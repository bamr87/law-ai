'use client'

import {
  fetchAutonomyCoverage,
  fetchAutonomyLegalbenchHistory,
  fetchAutonomyQuarantine,
  type AutonomyCoverage,
  type AutonomyLegalbenchHistory,
  type AutonomyLegalbenchSeries,
  type AutonomyQuarantine,
} from '@/lib/api'
import { useCallback, useEffect, useState } from 'react'

/**
 * Read-only autonomy dashboard (BL-20260511-03).
 *
 * Three questions about a self-driving repo that previously had no answer
 * outside a container shell: is the benchmark moving, where is the code
 * thinnest, and what is waiting on a human. Every panel is a *view* — nothing
 * here triggers a cycle, approves a document, or calls a model.
 *
 * Each panel reports absence explicitly (constitution §13). `history.jsonl`
 * and `coverage.xml` are CI artifacts a fresh checkout does not have, and the
 * honest rendering of that is "not measured yet", never an empty chart that
 * reads as a score of zero.
 */

interface PanelState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

const initial = <T,>(): PanelState<T> => ({
  data: null,
  error: null,
  loading: true,
})

export default function AutonomyDashboard() {
  const [history, setHistory] =
    useState<PanelState<AutonomyLegalbenchHistory>>(initial)
  const [coverage, setCoverage] = useState<PanelState<AutonomyCoverage>>(initial)
  const [quarantine, setQuarantine] =
    useState<PanelState<AutonomyQuarantine>>(initial)
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null)

  const load = useCallback(async () => {
    // Nothing is set before the first `await` on purpose: a synchronous
    // setState inside the mount effect cascades a render, and a refresh that
    // blanks three panels to skeletons is worse than one that swaps the
    // numbers in place when they arrive.
    const run = async <T,>(
      fn: () => Promise<T>,
      set: (s: PanelState<T>) => void,
    ) => {
      try {
        set({ data: await fn(), error: null, loading: false })
      } catch (err) {
        const message = err instanceof Error ? err.message : 'request failed'
        set({ data: null, error: message, loading: false })
      }
    }
    await Promise.all([
      run(() => fetchAutonomyLegalbenchHistory(), setHistory),
      run(fetchAutonomyCoverage, setCoverage),
      run(fetchAutonomyQuarantine, setQuarantine),
    ])
    setRefreshedAt(new Date().toISOString())
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">
          {refreshedAt
            ? `Last refreshed ${new Date(refreshedAt).toLocaleTimeString()}`
            : 'Loading…'}
        </p>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-slate-500 hover:bg-slate-800"
        >
          Refresh
        </button>
      </div>

      <Panel
        title="LegalBench accuracy over time"
        subtitle="One line per subset, oldest run first. Pinned to Ollama, so the numbers stay comparable."
        state={history}
      >
        <LegalbenchPanel data={history.data} />
      </Panel>

      <Panel
        title="Lowest-coverage modules"
        subtitle="The five thinnest-tested modules — the nightly test pillar's targets."
        state={coverage}
      >
        <CoveragePanel data={coverage.data} />
      </Panel>

      <Panel
        title="Recently quarantined documents"
        subtitle="The ten newest extractions waiting on a human. Nothing here has reached the graph."
        state={quarantine}
      >
        <QuarantinePanel data={quarantine.data} />
      </Panel>
    </div>
  )
}

function Panel<T>({
  title,
  subtitle,
  state,
  children,
}: {
  title: string
  subtitle: string
  state: PanelState<T>
  children: React.ReactNode
}) {
  return (
    <section
      aria-label={title}
      className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 shadow-sm"
    >
      <header className="mb-3">
        <h2 className="text-base font-semibold text-slate-100">{title}</h2>
        <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
      </header>
      {state.loading && (
        <p className="text-sm text-slate-500">Loading…</p>
      )}
      {state.error && (
        <p
          role="alert"
          className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300"
        >
          Failed to load: {state.error}
        </p>
      )}
      {!state.loading && !state.error && children}
    </section>
  )
}

function Unavailable({ what }: { what: string }) {
  return (
    <p className="rounded-md border border-slate-700 bg-slate-800/40 p-3 text-sm text-slate-400">
      Not measured yet — {what}
    </p>
  )
}

// ---------------------------------------------------------------------------
// LegalBench
// ---------------------------------------------------------------------------

function LegalbenchPanel({ data }: { data: AutonomyLegalbenchHistory | null }) {
  if (!data || !data.available || data.series.length === 0) {
    return (
      <Unavailable what="no eval run has written backend/var/legalbench/history.jsonl. Run `make test-legalbench`." />
    )
  }
  return (
    <ul className="space-y-3">
      {data.series.map((series) => (
        <li
          key={series.subset}
          className="flex flex-wrap items-center gap-3 rounded-md border border-slate-800 bg-slate-900/60 p-2"
        >
          <span className="min-w-40 font-mono text-xs text-slate-300">
            {series.subset}
          </span>
          <Sparkline series={series} />
          <span className="font-mono text-xs text-slate-200">
            {series.latest === null
              ? '—'
              : `${(series.latest * 100).toFixed(1)}%`}
          </span>
          <Delta deltaPp={series.delta_pp} />
        </li>
      ))}
    </ul>
  )
}

function Delta({ deltaPp }: { deltaPp: number | null }) {
  if (deltaPp === null) {
    return (
      <span className="text-xs text-slate-500" title="One run is not a trend">
        no trend
      </span>
    )
  }
  const tone =
    deltaPp > 0
      ? 'text-emerald-300'
      : deltaPp < 0
        ? 'text-red-300'
        : 'text-slate-400'
  return (
    <span className={`font-mono text-xs ${tone}`}>
      {deltaPp > 0 ? '+' : ''}
      {deltaPp.toFixed(1)}pp
    </span>
  )
}

const SPARK_W = 120
const SPARK_H = 24

/**
 * Inline SVG sparkline. Missing measurements break the line rather than
 * interpolating across them: a straight segment over a run that never
 * measured the subset would be an invented data point.
 */
export function Sparkline({ series }: { series: AutonomyLegalbenchSeries }) {
  const points = series.points
  const measured = points.filter((p): p is number => p !== null)
  const label =
    measured.length === 0
      ? `${series.subset}: no measurements`
      : `${series.subset}: ${measured.length} runs, latest ${(
          measured[measured.length - 1] * 100
        ).toFixed(1)}%`

  if (measured.length === 0) {
    return (
      <svg
        role="img"
        aria-label={label}
        width={SPARK_W}
        height={SPARK_H}
        viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      />
    )
  }

  const min = Math.min(...measured)
  const max = Math.max(...measured)
  const span = max - min || 1
  const step = points.length > 1 ? SPARK_W / (points.length - 1) : 0
  const segments: string[] = []
  let current: string[] = []
  points.forEach((value, i) => {
    if (value === null) {
      if (current.length) segments.push(current.join(' '))
      current = []
      return
    }
    const x = (i * step).toFixed(2)
    const y = (SPARK_H - ((value - min) / span) * SPARK_H).toFixed(2)
    current.push(`${current.length === 0 ? 'M' : 'L'}${x},${y}`)
  })
  if (current.length) segments.push(current.join(' '))

  return (
    <svg
      role="img"
      aria-label={label}
      width={SPARK_W}
      height={SPARK_H}
      viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      className="shrink-0"
    >
      {segments.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-sky-400"
        />
      ))}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Coverage
// ---------------------------------------------------------------------------

function CoveragePanel({ data }: { data: AutonomyCoverage | null }) {
  if (!data || !data.available || data.modules.length === 0) {
    return (
      <Unavailable what="no coverage.xml on disk. Run `make test-coverage`." />
    )
  }
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">
        Five lowest-coverage modules, ascending
      </caption>
      <thead>
        <tr className="text-xs uppercase tracking-wide text-slate-500">
          <th scope="col" className="pb-2 font-medium">
            Module
          </th>
          <th scope="col" className="pb-2 font-medium">
            Coverage
          </th>
          <th scope="col" className="pb-2 font-medium">
            Severity
          </th>
        </tr>
      </thead>
      <tbody>
        {data.modules.map((mod) => (
          <tr key={mod.module} className="border-t border-slate-800">
            <td className="py-1.5 font-mono text-xs text-slate-300">
              {mod.module}
            </td>
            <td className="py-1.5 font-mono text-xs text-slate-200">
              {mod.pct.toFixed(1)}%
            </td>
            <td className="py-1.5">
              <SeverityBadge severity={mod.severity} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const tone =
    severity === 'high'
      ? 'border-red-500/40 bg-red-500/10 text-red-300'
      : severity === 'med'
        ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
        : 'border-slate-700 bg-slate-800/50 text-slate-400'
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs ${tone}`}>
      {severity}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Quarantine
// ---------------------------------------------------------------------------

function QuarantinePanel({ data }: { data: AutonomyQuarantine | null }) {
  if (!data || !data.available) {
    return (
      <Unavailable what="the quarantine queue could not be read (is Postgres up?)." />
    )
  }
  if (data.documents.length === 0) {
    return (
      <p className="text-sm text-slate-400">
        Nothing in quarantine — every extraction has been reviewed.
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {data.documents.map((doc) => (
        <li
          key={doc.id}
          className="rounded-md border border-slate-800 bg-slate-900/60 p-2"
        >
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-mono text-xs text-slate-200">{doc.id}</span>
            <span className="rounded border border-slate-700 px-1.5 py-0.5 text-xs text-slate-400">
              {doc.kind}
            </span>
            <span className="text-xs text-slate-500">{doc.source}</span>
            <span className="ml-auto font-mono text-xs text-slate-300">
              conf {doc.confidence.toFixed(2)}
            </span>
          </div>
          {doc.reason && (
            <p className="mt-1 text-xs text-slate-500">{doc.reason}</p>
          )}
        </li>
      ))}
    </ul>
  )
}
