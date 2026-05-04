'use client'

import AgentTrace from '@/components/AgentTrace'
import {
  runAnalysis,
  type AnalysisRequest,
  type AnalysisResponse,
} from '@/lib/api'
import { useCallback, useState } from 'react'

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
  const [useLanggraph, setUseLanggraph] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)

  const submit = useCallback(async () => {
    if (!text.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const body = await runAnalysis({
        text,
        jurisdiction: jurisdiction || undefined,
        use_langgraph: useLanggraph || undefined,
      })
      setResult(body)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
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

      {submitting && <SkeletonResult />}

      {result && !submitting && <ResultPanel result={result} />}
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
          <strong className="font-semibold">Human review recommended.</strong>{' '}
          Overall confidence{' '}
          {Math.round(result.confidence * 100)}% is below the 70% HITL
          threshold. Treat this output as a draft.
        </div>
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
                <li key={i}>
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
