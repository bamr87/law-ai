'use client'

import type { AgentRun } from '@/lib/api'
import { useMemo, useState } from 'react'
import { TypeIcon, relativeTime } from './primitives'

/** One provenance event in the Recent Runs list, and the type filter above it. */

export function RunRow({
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
  const inputObj = (run as Record<string, unknown>).input as
    | Record<string, unknown>
    | undefined
  const isError =
    inputObj?.error === true || (run as Record<string, unknown>).error === true
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
              'inline-block w-3 text-center text-slate-400 transition ' +
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
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-slate-400">
          {run.latency_ms != null && (
            <span className="rounded bg-slate-800 px-1.5 py-0.5 tabular-nums">
              {Math.round(Number(run.latency_ms))} ms
            </span>
          )}
          {time && <span title={time.toISOString()}>{relativeTime(time)}</span>}
        </div>
      </button>
      {(run.path || run.method) && (
        <div className="mt-1 truncate pl-5 font-mono text-[10px] text-slate-400">
          {String(run.method ?? '')} {String(run.path ?? '')}
        </div>
      )}
      {expanded && (
        <div className="mt-2 space-y-2 border-t border-slate-800 pt-2 pl-5">
          {traceId && (
            <div className="flex items-center gap-2 text-[10px] text-slate-400">
              <span>trace_id</span>
              <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
                {traceId}
              </code>
              {onDrill && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDrill(traceId)
                  }}
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

// ---------------------------------------------------------------------------
// RunTypeTabs — filter runs by event type
// ---------------------------------------------------------------------------

export const RUN_TYPES = [
  'all',
  'http_request',
  'agent_call',
  'graph_query',
] as const

export function RunTypeTabs({
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
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-300')
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
