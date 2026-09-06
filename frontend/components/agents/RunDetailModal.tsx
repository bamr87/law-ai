'use client'

import { useFocusTrap } from '@/components/shell/Overlay'
import { fetchRunDetail, type AgentRun } from '@/lib/api'
import { useEffect, useState } from 'react'
import { SkeletonLines, TypeIcon, relativeTime } from './primitives'
import { useStableDismiss } from './useStableDismiss'

// ---------------------------------------------------------------------------
// RunDetailModal — fetches all events for one trace_id
// ---------------------------------------------------------------------------

export function RunDetailModal({
  traceId,
  onClose,
}: {
  traceId: string
  onClose: () => void
}) {
  const [events, setEvents] = useState<AgentRun[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const trapRef = useFocusTrap<HTMLDivElement>(true, useStableDismiss(onClose))

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
      style={{ zIndex: 'var(--z-drawer)' }}
      className="fixed inset-0 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Trapped like the launch modal above (BL-20260831-07). */}
      <div
        ref={trapRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Run details"
        className="w-full max-w-3xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl outline-none"
      >
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-100">Provenance Trace</h2>
            <p className="mt-0.5 font-mono text-[11px] text-slate-400">
              {traceId}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:text-slate-200"
          >
            ✕
          </button>
        </header>

        <div className="shell-panel-scroll max-h-[70vh] p-5">
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
                {events.length} event{events.length !== 1 ? 's' : ''} share this
                trace
              </div>
              <ol className="space-y-3">
                {events.map((ev, i) => {
                  const inp = (ev as Record<string, unknown>).input as
                    | Record<string, unknown>
                    | undefined
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
                        <div className="flex items-center gap-2 text-[10px] text-slate-400">
                          {ev.latency_ms != null && (
                            <span>{Math.round(Number(ev.latency_ms))} ms</span>
                          )}
                          {ev.confidence != null && (
                            <span>
                              conf {(Number(ev.confidence) * 100).toFixed(0)}%
                            </span>
                          )}
                          {ev.timestamp && (
                            <span>
                              {relativeTime(new Date(String(ev.timestamp)))}
                            </span>
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

export default RunDetailModal
