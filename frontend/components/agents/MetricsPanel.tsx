'use client'

import type { AgentMetric } from '@/lib/api'
import { relativeTime } from './primitives'

// ---------------------------------------------------------------------------
// MetricsPanel — per-agent aggregated metrics from /api/agents/metrics
// ---------------------------------------------------------------------------

export function MetricsPanel({
  loading,
  error,
  data,
  onSelectTrace,
}: {
  loading: boolean
  error: string | null
  data: {
    agents: AgentMetric[]
    window_size: number
    errors_total: number
  } | null
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
          No agent calls in the last {data.window_size} events. Run an agent to
          populate.
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
            <span className="ml-2 text-red-400">
              · {data.errors_total} error{data.errors_total !== 1 ? 's' : ''}
            </span>
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
              <tr
                key={m.agent}
                className="border-b border-slate-800/40 last:border-0"
              >
                <td className="py-2 pr-3 font-mono text-slate-200">
                  {m.agent}
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-300">
                  {m.count}
                  {m.error_count > 0 && (
                    <span className="ml-1 text-red-400">
                      ({m.error_count} err)
                    </span>
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
                    {m.success_rate != null
                      ? `${(m.success_rate * 100).toFixed(0)}%`
                      : '—'}
                  </span>
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.latency_p50_ms != null ? `${m.latency_p50_ms}ms` : '—'}
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.latency_p95_ms != null ? `${m.latency_p95_ms}ms` : '—'}
                </td>
                <td className="py-2 pr-3 tabular-nums text-slate-400">
                  {m.avg_confidence != null
                    ? `${(m.avg_confidence * 100).toFixed(0)}%`
                    : '—'}
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

export default MetricsPanel
