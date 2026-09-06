'use client'

import type { LocalAIHealth } from '@/lib/api'
import { SkeletonLines } from './primitives'

// ---------------------------------------------------------------------------
// HealthPanel — local AI system health overview
// ---------------------------------------------------------------------------

export function HealthPanel({
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

  // The chain is ordered, so the first configured + reachable tier is the one
  // that will actually serve the next request. Naming it explicitly beats
  // making operators infer it from a row of green dots.
  const chain = health.llm_chain ?? []
  const servingIndex = chain.findIndex(
    (p) => p.configured && p.reachable !== false,
  )

  const services: Array<{ label: string; reachable: boolean; detail: string }> =
    [
      ...chain.map((provider, i) => ({
        label: `${i + 1}. ${provider.provider}`,
        reachable: provider.configured && provider.reachable !== false,
        detail: !provider.configured
          ? (provider.reason ?? 'not configured')
          : provider.reachable === false
            ? (provider.error ?? provider.reason ?? 'unreachable')
            : `${provider.model ?? 'ready'}${i === servingIndex ? ' — serving' : ''}`,
      })),
      {
        label: 'Ollama host',
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

export default HealthPanel
