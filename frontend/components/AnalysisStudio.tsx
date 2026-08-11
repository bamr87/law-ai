'use client'

import AgentTrace from '@/components/AgentTrace'
import { LegalDisclaimerBanner } from '@/components/LegalDisclaimer'
import {
  newStreamId,
  openAgentStream,
  type AgentStepEvent,
} from '@/lib/agentStream'
import {
  runAnalysis,
  type AnalysisRequest,
  type AnalysisResponse,
} from '@/lib/api'
import { useCallback, useState } from 'react'

const HITL_THRESHOLD = 0.7

/**
 * Agents reporting in as they finish (spec 032). Renders nothing until the
 * first event lands, so a failed socket degrades to the plain skeleton
 * rather than showing an empty "live" panel that never fills.
 */
function LiveTrace({ steps }: { steps: AgentStepEvent[] }) {
  if (steps.length === 0) return null
  return (
    <section
      aria-labelledby="live-trace-heading"
      aria-live="polite"
      className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 px-4 py-3"
    >
      <h2
        id="live-trace-heading"
        className="mb-2 text-xs uppercase tracking-wider text-indigo-300"
      >
        Agents reporting
      </h2>
      <ul className="space-y-1 text-sm text-slate-300">
        {steps.map((step) => (
          <li key={`${step.agent}-${step.trace_id ?? ''}`} className="flex gap-2">
            <span aria-hidden="true">✓</span>
            <span className="font-medium text-slate-200">{step.agent}</span>
            <span className="text-slate-500">
              {Math.round(step.latency_ms)} ms
            </span>
            {step.degraded && (
              <span className="text-amber-300">degraded — no engine ran</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * Explain why review is required using the STRUCTURED flags the backend
 * now returns. The banner previously asserted "confidence is below the 70%
 * threshold" unconditionally, which is wrong whenever a degraded agent or
 * an unresolved citation triggered the flag instead.
 */
function reviewReason(result: AnalysisResponse): string {
  if (result.irac.degraded) {
    return (
      'No analysis engine ran for this request, so the output below is a ' +
      'placeholder — not a legal analysis. Do not rely on it.'
    )
  }
  if (result.precedents.degraded) {
    return (
      'Precedent search did not run, so no supporting authority was ' +
      'retrieved. Absence here does not mean no precedent exists.'
    )
  }
  if (result.irac.requires_review) {
    return (
      'The cited authorities could not all be verified against the ' +
      'knowledge graph. Check each citation before relying on it.'
    )
  }
  return (
    `Overall confidence ${Math.round(result.confidence * 100)}% is below the ` +
    `${Math.round(HITL_THRESHOLD * 100)}% threshold. Treat this as a draft.`
  )
}

const SAMPLE: AnalysisRequest = {
  text:
    'Plaintiff slipped on an unmarked wet floor in defendant grocery store, ' +
    'sustaining a fractured wrist. The floor had been mopped 30 minutes prior; ' +
    'no warning sign was placed. Plaintiff seeks damages for negligence under ' +
    'a premises-liability theory. Defendant contends the hazard was open and ' +
    'obvious and that plaintiff failed to exercise reasonable care.',
  jurisdiction: 'US-CA',
}

const JURISDICTIONS = [
  { value: '', label: 'Auto / unspecified' },
  { value: 'US', label: 'US (federal)' },
  { value: 'US-CA', label: 'California' },
  { value: 'US-NY', label: 'New York' },
  { value: 'US-TX', label: 'Texas' },
  { value: 'EU', label: 'EU' },
  { value: 'Other', label: 'Other' },
]

const MAX_LEN = 20_000

export default function AnalysisStudio() {
  const [text, setText] = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  // Spec 027: the LangGraph + Ollama workflow is the default engine.
  const [useLanggraph, setUseLanggraph] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [liveSteps, setLiveSteps] = useState<AgentStepEvent[]>([])

  const submit = useCallback(async () => {
    if (!text.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    setLiveSteps([])

    // Spec 032: subscribe BEFORE posting. `openAgentStream` resolves on the
    // server's `ready`, so by the time we POST the group membership exists
    // and step events land as each agent finishes. Streaming is strictly an
    // enhancement — if the socket fails we still run the analysis and the
    // REST response remains authoritative.
    const streamId = newStreamId()
    let socket: WebSocket | null = null
    try {
      socket = await openAgentStream(streamId, (event) => {
        if (event.type === 'agent_step') {
          setLiveSteps((prev) => [...prev, event])
        }
      })
    } catch {
      socket = null
    }

    try {
      const body = await runAnalysis({
        text,
        jurisdiction: jurisdiction || undefined,
        // Explicit boolean: the server defaults to true, so an omitted flag
        // would silently re-enable the engine when the user opted out.
        use_langgraph: useLanggraph,
        ...(socket ? { stream_id: streamId } : {}),
      })
      setResult(body)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      socket?.close()
      setSubmitting(false)
    }
  }, [text, jurisdiction, useLanggraph, submitting])

  const loadSample = () => {
    setText(SAMPLE.text)
    setJurisdiction(SAMPLE.jurisdiction ?? '')
  }

  const remaining = MAX_LEN - text.length

  return (
    <div className="space-y-6">
      {/* Input form */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <label
            htmlFor="analysis-text"
            className="text-xs uppercase tracking-wider text-slate-500"
          >
            Fact pattern
          </label>
          <button
            type="button"
            onClick={loadSample}
            className="text-xs text-indigo-300 underline-offset-2 hover:underline"
          >
            Load sample
          </button>
        </div>
        <textarea
          id="analysis-text"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_LEN))}
          onKeyDown={(e) => {
            // Cmd/Ctrl + Enter submits
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault()
              void submit()
            }
          }}
          placeholder="Paste a fact pattern, hypo, or exam prompt…"
          className="min-h-[180px] w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-relaxed text-slate-100 placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <label
              htmlFor="analysis-jur"
              className="text-xs uppercase tracking-wider text-slate-500"
            >
              Jurisdiction
            </label>
            <select
              id="analysis-jur"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
            >
              {JURISDICTIONS.map((j) => (
                <option key={j.value} value={j.value}>
                  {j.label}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slate-500">
              {remaining.toLocaleString()} chars remaining
            </span>
            <label
              htmlFor="use-langgraph"
              className="ml-2 flex cursor-pointer items-center gap-2 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
              title="Route through the LangGraph + Ollama workflow (real local LLM, slower)"
            >
              <input
                id="use-langgraph"
                type="checkbox"
                checked={useLanggraph}
                onChange={(e) => setUseLanggraph(e.target.checked)}
                className="h-3 w-3 accent-indigo-500"
              />
              Use local LLM (LangGraph + Ollama)
            </label>
          </div>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={submitting || !text.trim()}
            title="Run analysis (⌘/Ctrl + Enter)"
            className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:shadow-blue-500/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Analysing…' : 'Run analysis'}
            {!submitting && (
              <>
                <kbd className="hidden rounded border border-white/30 bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-normal text-white/80 sm:inline-block">
                  ⌘ ⏎
                </kbd>
                <span aria-hidden>→</span>
              </>
            )}
          </button>
        </div>
      </section>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
        >
          {error}
        </div>
      )}

      {submitting && <LiveTrace steps={liveSteps} />}
      {submitting && <SkeletonResult />}

      {result && !submitting && <ResultPanel result={result} />}
      {!result && !submitting && <LegalDisclaimerBanner className="mt-6" />}
    </div>
  )
}

function ResultPanel({ result }: { result: AnalysisResponse }) {
  return (
    <div className="space-y-6">
      {(result.phoenix_trace_url || result.langgraph_thread_id) && (
        <div className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
          <div className="font-semibold">Local LLM run (LangGraph + Ollama)</div>
          <div className="mt-1 grid gap-1 text-xs">
            {result.langgraph_thread_id && (
              <div>
                <span className="text-indigo-400">Thread:</span>{' '}
                <code className="rounded bg-slate-950/60 px-1 py-0.5">
                  {result.langgraph_thread_id}
                </code>
              </div>
            )}
            {result.phoenix_trace_url && (
              <div>
                <span className="text-indigo-400">Phoenix trace:</span>{' '}
                <a
                  href={result.phoenix_trace_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-300 underline-offset-2 hover:underline"
                >
                  {result.phoenix_trace_url}
                </a>
              </div>
            )}
            <div>
              <span className="text-indigo-400">Latency:</span>{' '}
              {(result.latency_ms / 1000).toFixed(2)}s
            </div>
          </div>
        </div>
      )}

      {result.requires_human_review && (
        <div
          role="alert"
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
        >
          <strong className="font-semibold">Human review required.</strong>{' '}
          {reviewReason(result)}
        </div>
      )}

      {/* UPL guardrail (BL-20260810-07): sits directly above generated
          analysis, where over-reliance is most likely. */}
      <LegalDisclaimerBanner />

      {result.irac.retrieval && (
        <section
          aria-labelledby="coverage-heading"
          className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-xs text-slate-400"
        >
          <h2
            id="coverage-heading"
            className="mb-1 text-xs uppercase tracking-wider text-slate-500"
          >
            Corpus coverage
          </h2>
          <p className="text-slate-300">
            {result.irac.retrieval.coverage_note ||
              `${result.irac.retrieval.result_count} passage(s) retrieved.`}
          </p>
          {result.irac.retrieval.queries.length > 0 && (
            <p className="mt-1 text-slate-500">
              Searched: {result.irac.retrieval.queries.join(' · ')}
            </p>
          )}
        </section>
      )}

      {/* IRAC card */}
      <section
        aria-labelledby="irac-heading"
        className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="irac-heading" className="text-lg font-semibold text-slate-100">
            IRAC Brief
          </h2>
          <span className="rounded bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">
            {Math.round(result.irac.confidence * 100)}% confidence
          </span>
        </div>
        <dl className="grid gap-4 sm:grid-cols-2">
          <IracField label="Issue" value={result.irac.issue} />
          <IracField label="Rule" value={result.irac.rule} />
          <IracField label="Application" value={result.irac.application} />
          <IracField label="Conclusion" value={result.irac.conclusion} />
        </dl>
        {result.irac.sources.length > 0 && (
          <div className="mt-5">
            <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
              Sources
            </h3>
            <ul className="space-y-1 text-sm">
              {result.irac.sources.map((s, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  {s.url ? (
                    <a
                      href={String(s.url)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-300 hover:underline"
                    >
                      {String(s.title ?? s.url)}
                    </a>
                  ) : (
                    <span className="text-slate-300">{String(s.title)}</span>
                  )}
                  {/* BL-20260810-02: an unresolved citation is exactly what a
                      reviewer must inspect, so it is labelled rather than
                      hidden. `verified` absent ⇒ path predates the check. */}
                  {s.verified === true && (
                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[11px] text-emerald-300">
                      verified in graph
                    </span>
                  )}
                  {s.verified === false && (
                    <span
                      title="This authority could not be resolved against the knowledge graph — verify it against the official record before relying on it."
                      className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300"
                    >
                      unverified
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Precedents */}
      <section
        aria-labelledby="prec-heading"
        className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="prec-heading" className="text-lg font-semibold text-slate-100">
            Relevant Precedents
          </h2>
          <span className="rounded bg-indigo-500/10 px-2 py-1 text-xs text-indigo-300">
            {result.precedents.precedents.length} found
          </span>
        </div>
        <p className="mb-4 text-sm text-slate-400">
          {result.precedents.summary}
        </p>
        <ul className="space-y-3">
          {result.precedents.precedents.map((p) => (
            <li
              key={p.case_id}
              className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-100">
                  {p.url ? (
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-blue-300"
                    >
                      {p.title}
                    </a>
                  ) : (
                    p.title
                  )}
                </h3>
                <span className="text-[11px] text-slate-500">
                  {p.court} · {p.year}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <div
                  className="h-1.5 flex-1 overflow-hidden rounded bg-slate-800"
                  aria-label={`Relevance ${Math.round(p.relevance_score * 100)}%`}
                >
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-indigo-500"
                    style={{ width: `${Math.round(p.relevance_score * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] text-slate-400">
                  {Math.round(p.relevance_score * 100)}%
                </span>
              </div>
              {p.distinguishing_factors.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
                  {p.distinguishing_factors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>

      {/* Agent trace */}
      <AgentTrace
        steps={result.agent_trace.map(
          (e) =>
            `${e.agent} · ${Math.round(e.confidence * 100)}% conf · ${Math.round(e.latency_ms)}ms`,
        )}
        confidence={result.confidence}
      />

      {/* Footer chip */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
        <span>
          Analysis{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
            {result.id}
          </code>{' '}
          · {result.latency_ms}ms · {new Date(result.timestamp).toLocaleString()}
        </span>
        {result.agent_trace[0]?.trace_id && (
          <span>
            trace_id{' '}
            <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
              {result.agent_trace[0].trace_id.slice(0, 8)}…
            </code>
          </span>
        )}
      </div>
    </div>
  )
}

function IracField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mb-1 text-xs uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className="text-sm leading-relaxed text-slate-200">{value}</dd>
    </div>
  )
}

function SkeletonResult() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading analysis"
      className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur"
    >
      <div className="h-4 w-1/3 animate-pulse rounded bg-slate-800" />
      <div className="h-3 w-full animate-pulse rounded bg-slate-800" />
      <div className="h-3 w-5/6 animate-pulse rounded bg-slate-800" />
      <div className="h-3 w-4/6 animate-pulse rounded bg-slate-800" />
    </div>
  )
}
