'use client'

import { useFocusTrap } from '@/components/shell/Overlay'
import { runAnalysis, type AgentInfo } from '@/lib/api'
import { useState } from 'react'
import { AGENT_DESCRIPTIONS } from './AgentCard'
import { useStableDismiss } from './useStableDismiss'

// ---------------------------------------------------------------------------
// AgentLaunchModal — run LegalAnalyst or PrecedentHunter
// ---------------------------------------------------------------------------

export function AgentLaunchModal({
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
  // Spec 027: the LangGraph + Ollama workflow is the default engine.
  const [useLangGraph, setUseLangGraph] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [resultTrace, setResultTrace] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(true, useStableDismiss(onClose))

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
      const firstTrace =
        resp.agent_trace.find((t) => t.trace_id)?.trace_id ?? null
      setResultTrace(firstTrace)
      const irac = resp.irac
      setResult(
        [
          `Mode: ${useLangGraph ? 'LangGraph (real Ollama)' : 'no-engine stub (degraded)'}`,
          `Issue: ${irac.issue}`,
          `Rule: ${irac.rule}`,
          `Application: ${irac.application}`,
          `Conclusion: ${irac.conclusion}`,
          `Confidence: ${(resp.confidence * 100).toFixed(0)}%`,
          resp.requires_human_review ? '⚠ Requires human review (HITL)' : '',
          resp.irac.sources.length > 0
            ? `Sources: ${resp.irac.sources
                .map((s) => s.title ?? s.url ?? '')
                .filter(Boolean)
                .join(', ')}`
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
      style={{ zIndex: 'var(--z-drawer)' }}
      className="fixed inset-0 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* BL-20260831-07: the dialog itself carries the trap — focus moves in
          on open, Tab cannot leave, Escape closes, focus returns to the
          launch button. The wrapper above stays a plain click-to-dismiss
          scrim (aria-hidden would hide the dialog inside it). */}
      <div
        ref={trapRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Run ${agent.name}`}
        className="w-full max-w-xl rounded-xl border border-slate-700 bg-slate-900 shadow-2xl outline-none"
      >
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-100">Run {agent.name}</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {AGENT_DESCRIPTIONS[agent.name]}
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

        <form
          onSubmit={(e) => {
            void handleSubmit(e)
          }}
          className="space-y-3 p-5"
        >
          <div>
            <label
              htmlFor="agent-input-text"
              className="mb-1 block text-xs font-medium text-slate-400"
            >
              Legal Issue / Case Text
            </label>
            <textarea
              id="agent-input-text"
              rows={4}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Describe the legal issue or paste a case fact pattern…"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus-ring"
              required
            />
          </div>
          <div>
            <label
              htmlFor="agent-jurisdiction"
              className="mb-1 block text-xs font-medium text-slate-400"
            >
              Jurisdiction (optional)
            </label>
            <input
              id="agent-jurisdiction"
              type="text"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              placeholder="e.g. Colorado, 10th Circuit"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus-ring"
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
              <span className="font-medium">
                Real mode (LangGraph + Ollama)
              </span>
              <span className="block text-[11px] text-slate-500">
                When off, returns a canned IRAC for fast UI testing (legacy
                stub). When on, invokes the real LegalWorkflow against Ollama
                and Neo4j.
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

export default AgentLaunchModal
