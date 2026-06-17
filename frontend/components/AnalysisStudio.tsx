'use client'

import AgentTrace from '@/components/AgentTrace'
import { useRunAnalysis } from '@/lib/queries'
import {
  Badge,
  Button,
  ErrorState,
  Page,
  Panel,
  Select,
  SkeletonLines,
  Textarea,
} from '@/components/ui'
import type { AnalysisRequest, AnalysisResponse } from '@/lib/api'
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
  const analysis = useRunAnalysis()

  const submit = useCallback(() => {
    if (!text.trim() || analysis.isPending) return
    analysis.mutate({
      text,
      jurisdiction: jurisdiction || undefined,
      use_langgraph: useLanggraph || undefined,
    })
  }, [text, jurisdiction, useLanggraph, analysis])

  const loadSample = () => {
    setText(SAMPLE.text)
    setJurisdiction(SAMPLE.jurisdiction ?? '')
  }

  const remaining = MAX_LEN - text.length
  const result = analysis.data

  return (
    <Page
      eyebrow="Studio"
      title="Analysis Studio"
      tagline={
        <>
          Paste a fact pattern and run the{' '}
          <code className="text-ink">LegalAnalyst</code> and{' '}
          <code className="text-ink">PrecedentHunter</code> crews in parallel.
          Every run is logged to the audit store with a HITL flag when
          confidence drops below 70%.
        </>
      }
    >
      <Panel
        title="Fact pattern"
        actions={
          <button
            type="button"
            onClick={loadSample}
            className="text-xs font-medium text-brand underline-offset-2 hover:underline"
          >
            Load sample
          </button>
        }
      >
        <label htmlFor="analysis-text" className="sr-only">
          Fact pattern
        </label>
        <Textarea
          id="analysis-text"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_LEN))}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
          }}
          placeholder="Paste a fact pattern, hypo, or exam prompt…"
          className="min-h-[180px] leading-relaxed"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <label
              htmlFor="analysis-jur"
              className="text-xs font-medium text-muted"
            >
              Jurisdiction
            </label>
            <div className="w-44">
              <Select
                id="analysis-jur"
                value={jurisdiction}
                onChange={(e) => setJurisdiction(e.target.value)}
                className="h-8 py-1"
              >
                {JURISDICTIONS.map((j) => (
                  <option key={j.value} value={j.value}>
                    {j.label}
                  </option>
                ))}
              </Select>
            </div>
            <span className="text-[11px] text-subtle">
              {remaining.toLocaleString()} chars left
            </span>
            <label
              htmlFor="use-langgraph"
              className="ml-1 flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-muted"
              title="Route through the LangGraph + Ollama workflow (real local LLM, slower)"
            >
              <input
                id="use-langgraph"
                type="checkbox"
                checked={useLanggraph}
                onChange={(e) => setUseLanggraph(e.target.checked)}
                className="h-3 w-3 accent-[var(--color-brand)]"
              />
              Local LLM (LangGraph + Ollama)
            </label>
          </div>
          <Button
            onClick={submit}
            disabled={!text.trim() || analysis.isPending}
            title="Run analysis (⌘/Ctrl + Enter)"
          >
            {analysis.isPending ? (
              'Analysing…'
            ) : (
              <>
                Run analysis
                <kbd className="hidden rounded border border-white/30 bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-normal text-white/80 sm:inline-block">
                  ⌘ ⏎
                </kbd>
              </>
            )}
          </Button>
        </div>
      </Panel>

      {analysis.isError && (
        <ErrorState
          message={
            (analysis.error as Error)?.message ?? 'Analysis failed'
          }
        />
      )}

      {analysis.isPending && (
        <Panel title="Running analysis…">
          <SkeletonLines rows={4} />
        </Panel>
      )}

      {result && !analysis.isPending && <ResultPanels result={result} />}
    </Page>
  )
}

function ResultPanels({ result }: { result: AnalysisResponse }) {
  return (
    <>
      {(result.phoenix_trace_url || result.langgraph_thread_id) && (
        <div className="rounded-lg border border-brand/30 bg-brand-soft px-4 py-3 text-sm text-brand">
          <div className="font-semibold text-ink">
            Local LLM run (LangGraph + Ollama)
          </div>
          <div className="mt-1 grid gap-1 text-xs text-muted">
            {result.langgraph_thread_id && (
              <div>
                Thread:{' '}
                <code className="text-ink">{result.langgraph_thread_id}</code>
              </div>
            )}
            {result.phoenix_trace_url && (
              <div>
                Phoenix trace:{' '}
                <a
                  href={result.phoenix_trace_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand underline-offset-2 hover:underline"
                >
                  {result.phoenix_trace_url}
                </a>
              </div>
            )}
            <div>Latency: {(result.latency_ms / 1000).toFixed(2)}s</div>
          </div>
        </div>
      )}

      {result.requires_human_review && (
        <div
          role="alert"
          className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          <strong className="font-semibold text-ink">
            Human review recommended.
          </strong>{' '}
          Overall confidence {Math.round(result.confidence * 100)}% is below the
          70% HITL threshold. Treat this output as a draft.
        </div>
      )}

      <Panel
        title="IRAC Brief"
        actions={
          <Badge tone="success">
            {Math.round(result.irac.confidence * 100)}% confidence
          </Badge>
        }
      >
        <dl className="grid gap-4 sm:grid-cols-2">
          <IracField label="Issue" value={result.irac.issue} />
          <IracField label="Rule" value={result.irac.rule} />
          <IracField label="Application" value={result.irac.application} />
          <IracField label="Conclusion" value={result.irac.conclusion} />
        </dl>
        {result.irac.sources.length > 0 && (
          <div className="mt-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">
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
                      className="text-brand hover:underline"
                    >
                      {String(s.title ?? s.url)}
                    </a>
                  ) : (
                    <span className="text-muted">{String(s.title)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>

      <Panel
        title="Relevant Precedents"
        actions={
          <Badge tone="brand">
            {result.precedents.precedents.length} found
          </Badge>
        }
      >
        <p className="mb-4 text-sm text-muted">{result.precedents.summary}</p>
        <ul className="space-y-3">
          {result.precedents.precedents.map((p) => (
            <li
              key={p.case_id}
              className="rounded-lg border border-border bg-surface-2 p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">
                  {p.url ? (
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-brand"
                    >
                      {p.title}
                    </a>
                  ) : (
                    p.title
                  )}
                </h3>
                <span className="text-[11px] text-subtle">
                  {p.court} · {p.year}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <div
                  className="h-1.5 flex-1 overflow-hidden rounded-full bg-border"
                  aria-label={`Relevance ${Math.round(p.relevance_score * 100)}%`}
                >
                  <div
                    className="h-full rounded-full bg-brand"
                    style={{ width: `${Math.round(p.relevance_score * 100)}%` }}
                  />
                </div>
                <span className="text-[11px] text-muted">
                  {Math.round(p.relevance_score * 100)}%
                </span>
              </div>
              {p.distinguishing_factors.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted">
                  {p.distinguishing_factors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </Panel>

      <AgentTrace
        steps={result.agent_trace.map(
          (e) =>
            `${e.agent} · ${Math.round(e.confidence * 100)}% conf · ${Math.round(e.latency_ms)}ms`,
        )}
        confidence={result.confidence}
      />

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-subtle">
        <span>
          Analysis <code className="text-muted">{result.id}</code> ·{' '}
          {result.latency_ms}ms ·{' '}
          {new Date(result.timestamp).toLocaleString()}
        </span>
        {result.agent_trace[0]?.trace_id && (
          <span>
            trace_id{' '}
            <code className="text-muted">
              {result.agent_trace[0].trace_id.slice(0, 8)}…
            </code>
          </span>
        )}
      </div>
    </>
  )
}

function IracField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mb-1 text-xs font-semibold uppercase tracking-wide text-subtle">
        {label}
      </dt>
      <dd className="text-sm leading-relaxed text-ink">{value}</dd>
    </div>
  )
}
