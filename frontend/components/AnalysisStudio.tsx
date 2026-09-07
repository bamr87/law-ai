'use client'

import AgentTrace from '@/components/AgentTrace'
import { LegalDisclaimerBanner } from '@/components/LegalDisclaimer'
import {
  newStreamId,
  openAgentStream,
  type AgentStepEvent,
  type AgentStreamStatus,
} from '@/lib/agentStream'
import {
  createShareLink,
  fetchAnalysis,
  runAnalysis,
  type AnalysisRequest,
  type AnalysisResponse,
  type Attribution,
  type ShareLink,
} from '@/lib/api'
import { useCallback, useEffect, useState } from 'react'

const HITL_THRESHOLD = 0.7

/**
 * Agents reporting in as they finish (spec 032). Renders nothing until the
 * first event lands, so a failed socket degrades to the plain skeleton
 * rather than showing an empty "live" panel that never fills.
 */
function LiveTrace({
  steps,
  writing,
  live,
  connection,
}: {
  steps: AgentStepEvent[]
  writing: { agent: string; chars: number; model?: string } | null
  live: boolean
  /**
   * Connection state of the run's socket (BL-20260905-79). A dropped stream
   * used to freeze the trace with no explanation, which reads as a stalled
   * analysis rather than a lost connection.
   */
  connection?: AgentStreamStatus
}) {
  const dropped = live && connection && connection !== 'live'
  // A drop before the first step still has something to say, so the panel
  // opens for that case even with nothing to list.
  if (steps.length === 0 && writing === null && !dropped) return null
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
        {live ? 'Agents reporting' : 'Agents reported'}
      </h2>
      {dropped && (
        <p role="status" className="mb-2 text-xs text-amber-300">
          {connection === 'reconnecting'
            ? 'Reconnecting…'
            : 'Live trace disconnected — the analysis still finishes below.'}
        </p>
      )}
      <ul className="space-y-1 text-sm text-slate-300">
        {steps.map((step) => (
          <li
            key={`${step.agent}-${step.trace_id ?? ''}`}
            className="flex gap-2"
          >
            <span aria-hidden="true">✓</span>
            <span className="font-medium text-slate-200">{step.agent}</span>
            <span className="text-slate-400">
              {Math.round(step.latency_ms)} ms
            </span>
            {step.degraded && (
              <span className="text-amber-300">degraded — no engine ran</span>
            )}
          </li>
        ))}
        {writing && (
          <li className="flex gap-2" data-testid="analysis-writing">
            <span aria-hidden="true">✍️</span>
            <span className="font-medium text-slate-200">{writing.agent}</span>
            <span className="text-slate-400">
              writing… {writing.chars.toLocaleString()} characters
              {writing.model ? ` · ${writing.model}` : ''}
            </span>
          </li>
        )}
      </ul>
    </section>
  )
}

/**
 * The issuing authority behind one source (constitution §13, BL-20260803-04).
 *
 * Court, date and binding/persuasive come off the `:Case` node the citation
 * resolved to — never from model prose. An incomplete attribution is called
 * out instead of rendered as an empty gap, because "we do not know which court
 * said this" is the fact a reader needs.
 */
function SourceAttribution({
  attribution,
}: {
  attribution?: Attribution | null
}) {
  if (!attribution) return null
  const { court, decided_at: decidedAt, authority } = attribution
  if (!court || !decidedAt) {
    return (
      <span
        title="This source carries no issuing authority (court and decision date) from the knowledge graph, so it is pinned for human review."
        className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300"
      >
        no issuing authority
      </span>
    )
  }
  return (
    <span className="text-[11px] text-slate-400">
      {court} · {decidedAt}
      {authority && authority !== 'unknown' ? ` · ${authority}` : ''}
    </span>
  )
}

/**
 * The issuing authority behind one retrieved precedent (BL-20260905-84).
 *
 * The row already prints the court and the year off the `:Case` node; what a
 * reader cannot get from those is whether the case *binds* the jurisdiction
 * they asked about. That is exactly what `attribution.authority` records, and
 * until now it travelled to the browser and was never drawn. An incomplete
 * attribution is labelled rather than silently omitted — a precedent nobody
 * can attribute is the one to check first.
 */
function PrecedentAuthority({
  attribution,
}: {
  attribution?: Attribution | null
}) {
  const court = attribution?.court
  const decidedAt = attribution?.decided_at
  if (!court || !decidedAt) {
    return (
      <span
        title="This precedent carries no complete issuing authority (court and decision date) from the knowledge graph, so the set is pinned for human review."
        className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300"
      >
        no issuing authority
      </span>
    )
  }
  const authority = attribution?.authority ?? 'unknown'
  const weight =
    authority === 'binding'
      ? 'bg-emerald-500/10 text-emerald-300'
      : authority === 'persuasive'
        ? 'bg-sky-500/10 text-sky-300'
        : 'bg-slate-700/40 text-slate-400'
  return (
    <>
      <span className="text-[11px] text-slate-400">
        {decidedAt}
        {attribution?.jurisdiction ? ` · ${attribution.jurisdiction}` : ''}
      </span>
      <span
        title={
          authority === 'unknown'
            ? 'Binding force is unknown: the graph does not record a jurisdiction for this court, or none was requested.'
            : `This authority is ${authority} for the requested jurisdiction.`
        }
        className={`rounded px-1.5 py-0.5 text-[11px] ${weight}`}
      >
        {authority}
      </span>
    </>
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
      'knowledge graph, or one of them names no issuing court and date. ' +
      'Check each citation before relying on it.'
    )
  }
  if (result.precedents.requires_review) {
    return (
      'At least one retrieved precedent carries no issuing authority ' +
      '(court and decision date), so it cannot be weighed as binding or ' +
      'persuasive without checking the official record.'
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
  // BL-20260810-13: resume a durable LangGraph thread. Pre-filled from the
  // last response so "run again on the same thread" is one click.
  const [threadId, setThreadId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // Characters the last edit dropped for exceeding MAX_LEN (BL-20260831-10).
  // Reset by the next edit that fits, so the warning never outlives its cause.
  const [dropped, setDropped] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [liveSteps, setLiveSteps] = useState<AgentStepEvent[]>([])
  // Whether the run's socket is still attached (BL-20260905-79). Reset at the
  // start of every submit; only ever shown while a run is in flight.
  const [connection, setConnection] = useState<AgentStreamStatus>('live')
  // BL-20260905-11: what the analyst has produced so far, while it is still
  // producing it. The IRAC pass is the slow one (56-103s on the xAI tier), and
  // a page that shows nothing for a minute reads as broken.
  const [writing, setWriting] = useState<{
    agent: string
    chars: number
    model?: string
  } | null>(null)

  // BL-20260429-25: `?id=an-…` reloads a persisted run, so the permalink
  // below survives a refresh, a new tab, or a colleague's inbox. A run that
  // was never persisted (or was archived) resolves to null and leaves an
  // empty studio rather than an error.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id')
    if (!id) return
    let cancelled = false
    void fetchAnalysis(id)
      .then((run) => {
        if (cancelled || !run) return
        setResult(run)
        setText(run.request?.text ?? '')
        setJurisdiction(run.request?.jurisdiction ?? '')
      })
      .catch(() => {
        /* a stale permalink is not an error worth shouting about */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const submit = useCallback(async () => {
    if (!text.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    setLiveSteps([])
    setWriting(null)
    setConnection('live')

    // Spec 032: subscribe BEFORE posting. `openAgentStream` resolves on the
    // server's `ready`, so by the time we POST the group membership exists
    // and step events land as each agent finishes. Streaming is strictly an
    // enhancement — if the socket fails we still run the analysis and the
    // REST response remains authoritative.
    const streamId = newStreamId()
    let socket: WebSocket | null = null
    try {
      socket = await openAgentStream(
        streamId,
        (event) => {
          if (event.type === 'agent_step') {
            setLiveSteps((prev) => [...prev, event])
            setWriting((prev) => (prev?.agent === event.agent ? null : prev))
          } else if (event.type === 'analysis_token') {
            // Progress, not content: the deltas are a JSON payload being
            // written, so the count is shown rather than half-parsed prose.
            setWriting({
              agent: event.agent,
              chars: event.chars,
              ...(event.model ? { model: event.model } : {}),
            })
          }
        },
        { onStatus: setConnection },
      )
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
        ...(threadId.trim() ? { thread_id: threadId.trim() } : {}),
        ...(socket ? { stream_id: streamId } : {}),
      })
      setResult(body)
      if (body.langgraph_thread_id) setThreadId(body.langgraph_thread_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      socket?.close()
      setSubmitting(false)
    }
  }, [text, jurisdiction, useLanggraph, threadId, submitting])

  const loadSample = () => {
    setText(SAMPLE.text)
    setJurisdiction(SAMPLE.jurisdiction ?? '')
    setDropped(0)
  }

  const remaining = MAX_LEN - text.length

  return (
    <div className="space-y-6">
      {/* Input form */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <label
            htmlFor="analysis-text"
            className="text-xs uppercase tracking-wider text-slate-400"
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
          onChange={(e) => {
            // BL-20260831-10: a paste longer than the cap used to lose its
            // tail in silence — the counter simply read "0 chars remaining".
            // Trim, then say exactly how much did not make it.
            const over = e.target.value.length - MAX_LEN
            setDropped(over > 0 ? over : 0)
            setText(e.target.value.slice(0, MAX_LEN))
          }}
          onKeyDown={(e) => {
            // Cmd/Ctrl + Enter submits
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault()
              void submit()
            }
          }}
          placeholder="Paste a fact pattern, hypo, or exam prompt…"
          className="min-h-[180px] w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-relaxed text-slate-100 placeholder-slate-600 focus:border-indigo-500 focus-ring"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <label
              htmlFor="analysis-jur"
              className="text-xs uppercase tracking-wider text-slate-400"
            >
              Jurisdiction
            </label>
            <select
              id="analysis-jur"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-indigo-500 focus-ring"
            >
              {JURISDICTIONS.map((j) => (
                <option key={j.value} value={j.value}>
                  {j.label}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slate-400">
              {remaining.toLocaleString()} chars remaining
            </span>
            {dropped > 0 && (
              <span
                role="status"
                data-testid="truncation-warning"
                className="text-[11px] text-amber-300"
              >
                Trimmed to {MAX_LEN.toLocaleString()} characters;{' '}
                {dropped.toLocaleString()} character
                {dropped === 1 ? ' was' : 's were'} not kept.
              </span>
            )}
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
            <label
              htmlFor="analysis-thread"
              className="ml-2 text-xs uppercase tracking-wider text-slate-400"
            >
              Resume thread
            </label>
            <input
              id="analysis-thread"
              value={threadId}
              onChange={(e) => setThreadId(e.target.value)}
              placeholder="lwf-…"
              title="Continue a previous run's LangGraph thread (leave blank to start a new one)"
              className="w-40 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-200 placeholder-slate-600 focus:border-indigo-500 focus-ring"
            />
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

      {/* BL-20260905-22: the trace outlives the run that produced it. The
          REST response can land within a few hundred milliseconds on the
          degraded path, and unmounting the panel with `submitting` threw the
          streamed detail away before anyone could read it. `liveSteps` is
          cleared by the next submit, so this never shows a stale run. */}
      {(submitting || liveSteps.length > 0) && (
        <LiveTrace
          steps={liveSteps}
          writing={submitting ? writing : null}
          live={submitting}
          connection={connection}
        />
      )}
      {submitting && <SkeletonResult />}

      {result && !submitting && <ResultPanel result={result} />}
      {!result && !submitting && <LegalDisclaimerBanner className="mt-6" />}
    </div>
  )
}

/**
 * The permalink for a persisted run (BL-20260429-25) and the "save & share"
 * control beside it (BL-20260429-26). Both are rendered as plain text/links
 * rather than copy buttons: the URL is the thing worth having, and selecting
 * it works everywhere, including where the clipboard API is blocked.
 *
 * Sharing needs a signed-in account, so the failure path is the common one
 * here — it surfaces the backend's own wording instead of a guess.
 */
function Permalink({ id }: { id: string }) {
  const href = `/analysis?id=${encodeURIComponent(id)}`
  const [slugInput, setSlugInput] = useState('')
  const [link, setLink] = useState<ShareLink | null>(null)
  const [sharing, setSharing] = useState(false)
  const [shareError, setShareError] = useState<string | null>(null)

  const share = async () => {
    setSharing(true)
    setShareError(null)
    try {
      setLink(
        await createShareLink(id, {
          ...(slugInput.trim() ? { slug: slugInput.trim().toLowerCase() } : {}),
        }),
      )
    } catch (e) {
      setShareError(e instanceof Error ? e.message : 'Share failed')
    } finally {
      setSharing(false)
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-xs text-slate-400">
      <div>
        <span className="text-slate-400">Permalink:</span>{' '}
        <a
          href={href}
          className="text-blue-300 underline-offset-2 hover:underline"
        >
          {href}
        </a>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="share-slug" className="text-slate-400">
          Share as
        </label>
        <input
          id="share-slug"
          value={slugInput}
          onChange={(e) => setSlugInput(e.target.value)}
          placeholder="optional-slug"
          className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-slate-200"
        />
        <button
          type="button"
          onClick={() => void share()}
          disabled={sharing}
          className="rounded border border-indigo-500/50 px-2 py-1 text-indigo-300 hover:bg-indigo-500/10 disabled:opacity-50"
        >
          {sharing ? 'Creating…' : 'Create share link'}
        </button>
      </div>
      {link && (
        <div>
          <span className="text-slate-400">Shareable URL:</span>{' '}
          <a
            href={link.url}
            className="text-emerald-300 underline-offset-2 hover:underline"
          >
            {link.url}
          </a>
        </div>
      )}
      {shareError && (
        <p role="status" className="text-amber-300">
          {shareError}
        </p>
      )}
    </div>
  )
}

/**
 * Which degraded path produced this row, for payloads old and new.
 *
 * The backend now says so in `degraded_reason` (BL-20260810-16); before that
 * field existed the only signal was the marker the fallback puts at the head
 * of `rule`, and a persisted run from then still has to render correctly.
 */
function degradedKind(
  irac: AnalysisResponse['irac'],
): 'engine_unavailable' | 'offline_fallback' {
  if (irac.degraded_reason) return irac.degraded_reason
  if (irac.rule?.includes('[OFFLINE FALLBACK]')) return 'offline_fallback'
  return 'engine_unavailable'
}

/**
 * What to do about a run that produced no analysis (BL-20260810-16).
 *
 * A degraded refusal used to render exactly like a real answer — IRAC card,
 * green "0% confidence" pill, precedent list — which is the one presentation
 * a legal tool must never give a non-answer. This replaces all of that with
 * the engine's state and the command that fixes it, and the guidance differs
 * by kind: `make local-ai-up` is the right advice only when the local engine
 * is the one that could not start.
 */
function EngineStatePanel({ result }: { result: AnalysisResponse }) {
  const kind = degradedKind(result.irac)
  return (
    <section
      role="status"
      data-testid="engine-state"
      aria-labelledby="engine-state-heading"
      className="rounded-2xl border border-red-500/40 bg-red-500/10 p-6"
    >
      <h2
        id="engine-state-heading"
        className="text-lg font-semibold text-red-200"
      >
        {kind === 'engine_unavailable'
          ? 'Local LLM engine offline — no analysis was produced'
          : 'No LLM provider reachable — no analysis was produced'}
      </h2>
      <p className="mt-2 text-sm text-red-100/90">
        {kind === 'engine_unavailable' ? (
          <>
            The analysis engine could not start, so nothing below is legal
            analysis. Start Ollama with{' '}
            <code className="rounded bg-slate-950/60 px-1 py-0.5 font-mono">
              make local-ai-up
            </code>{' '}
            (or configure a hosted tier in{' '}
            <code className="rounded bg-slate-950/60 px-1 py-0.5 font-mono">
              LLM_PROVIDER_CHAIN
            </code>
            ) and run this again.
          </>
        ) : (
          <>
            Every tier in{' '}
            <code className="rounded bg-slate-950/60 px-1 py-0.5 font-mono">
              LLM_PROVIDER_CHAIN
            </code>{' '}
            failed. Check the Claude credentials (or{' '}
            <code className="rounded bg-slate-950/60 px-1 py-0.5 font-mono">
              make xai-login
            </code>
            ) and the chain configuration, then run this again. Starting Ollama
            only helps if it is one of the configured tiers.
          </>
        )}
      </p>
      {/* The refusal text the backend wrote, verbatim: it names the reason
          (probe failure, missing credential) that this panel generalises. */}
      <p className="mt-3 text-xs text-red-200/70">{result.irac.rule}</p>
    </section>
  )
}

function ResultPanel({ result }: { result: AnalysisResponse }) {
  // A run with no engine behind it gets the engine's state, not a brief —
  // no confidence pill, no coverage envelope, no precedent list to mistake
  // for retrieved authority (BL-20260810-16).
  if (result.irac.degraded) {
    return (
      <div className="space-y-6">
        <Permalink id={result.id} />
        {result.requires_human_review && (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
          >
            <strong className="font-semibold">Human review required.</strong>{' '}
            {reviewReason(result)}
          </div>
        )}
        <LegalDisclaimerBanner />
        <EngineStatePanel result={result} />
        <section
          aria-labelledby="no-analysis-heading"
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 text-sm text-slate-400"
        >
          <h2
            id="no-analysis-heading"
            className="text-xs uppercase tracking-wider text-slate-400"
          >
            No analysis produced
          </h2>
          <p className="mt-2">
            No IRAC brief, no retrieval and no precedents were produced for this
            request. The run is kept for auditability only.
          </p>
        </section>
        <AgentTrace
          steps={result.agent_trace.map(
            (e) =>
              `${e.agent} · ${Math.round(e.confidence * 100)}% conf · ${Math.round(e.latency_ms)}ms`,
          )}
          confidence={result.confidence}
        />
      </div>
    )
  }

  // BL-20260906-10: `trace_url` is the name going forward; `phoenix_trace_url`
  // is the deprecated alias the server still emits for older clients.
  const traceUrl = result.trace_url ?? result.phoenix_trace_url

  return (
    <div className="space-y-6">
      <Permalink id={result.id} />
      {(traceUrl || result.langgraph_thread_id) && (
        <div className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">
          <div className="font-semibold">
            Local LLM run (LangGraph + Ollama)
          </div>
          <div className="mt-1 grid gap-1 text-xs">
            {result.langgraph_thread_id && (
              <div>
                <span className="text-indigo-400">Thread:</span>{' '}
                <code className="rounded bg-slate-950/60 px-1 py-0.5">
                  {result.langgraph_thread_id}
                </code>
                {result.resumed && (
                  <span className="ml-2 rounded bg-indigo-900/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-indigo-200">
                    resumed
                  </span>
                )}
              </div>
            )}
            {traceUrl && (
              <div>
                <span className="text-indigo-400">Trace:</span>{' '}
                <a
                  href={traceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-300 underline-offset-2 hover:underline"
                >
                  {traceUrl}
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
            className="mb-1 text-xs uppercase tracking-wider text-slate-400"
          >
            Corpus coverage
          </h2>
          <p className="text-slate-300">
            {result.irac.retrieval.coverage_note ||
              `${result.irac.retrieval.result_count} passage(s) retrieved.`}
          </p>
          {/* BL-20260811-18: the backend computes `jurisdiction_absent`, but
              folded into the prose note above it is easy to skim past. A
              jurisdictionally-lopsided result set changes what the answer is
              worth, so it gets its own live-region callout — not just a row
              in the envelope below. */}
          {result.irac.retrieval.jurisdiction_absent &&
            result.irac.retrieval.jurisdiction_requested && (
              <p
                role="status"
                data-testid="jurisdiction-absent"
                className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-200"
              >
                No results from the requested jurisdiction{' '}
                <span className="font-mono">
                  {result.irac.retrieval.jurisdiction_requested}
                </span>
                . The passages below come from{' '}
                {result.irac.retrieval.jurisdictions_present?.length
                  ? result.irac.retrieval.jurisdictions_present.join(', ')
                  : 'other jurisdictions'}{' '}
                and are persuasive at best.
              </p>
            )}
          {result.irac.retrieval.queries.length > 0 && (
            <p className="mt-1 text-slate-400">
              Searched: {result.irac.retrieval.queries.join(' · ')}
            </p>
          )}
          {/* Structured envelope rows (BL-20260803-02): the prose note above
              is the model-facing text; these are the fields a reviewer scans. */}
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-slate-400">
            {(result.irac.retrieval.jurisdictions_present?.length ?? 0) > 0 && (
              <>
                <dt>Jurisdictions present</dt>
                <dd className="text-slate-300">
                  {result.irac.retrieval.jurisdictions_present?.join(', ')}
                </dd>
              </>
            )}
            {result.irac.retrieval.jurisdiction_absent &&
              result.irac.retrieval.jurisdiction_requested && (
                <>
                  <dt>Jurisdiction absent</dt>
                  <dd className="text-amber-300">
                    {result.irac.retrieval.jurisdiction_requested} — nothing
                    retrieved from the requested jurisdiction
                  </dd>
                </>
              )}
            {(result.irac.retrieval.boosted_count ?? 0) > 0 && (
              <>
                <dt>Ranking boost</dt>
                <dd data-testid="retrieval-boost" className="text-indigo-300">
                  {result.irac.retrieval.boosted_count} passage(s) promoted
                  because {result.irac.retrieval.boost_source || 'a matter'} had
                  already verified them — this order is not the corpus&rsquo;s
                  own.
                </dd>
              </>
            )}
            {(result.irac.retrieval.date_earliest ||
              result.irac.retrieval.date_latest) && (
              <>
                <dt>Decision dates</dt>
                <dd className="text-slate-300">
                  {result.irac.retrieval.date_earliest ?? '?'} –{' '}
                  {result.irac.retrieval.date_latest ?? '?'}
                </dd>
              </>
            )}
          </dl>
        </section>
      )}

      {/* IRAC card */}
      <section
        aria-labelledby="irac-heading"
        className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2
            id="irac-heading"
            className="text-lg font-semibold text-slate-100"
          >
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
            <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-400">
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
                  {/* BL-20260803-04: §13 — every source names the authority
                      that issued it. Shown, not just carried: a court and a
                      date on the page are what let a reader tell binding law
                      from persuasive, and their absence is labelled rather
                      than left blank. */}
                  <SourceAttribution attribution={s.attribution} />
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
          <h2
            id="prec-heading"
            className="text-lg font-semibold text-slate-100"
          >
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
                <span className="text-[11px] text-slate-400">
                  {p.court} · {p.year}
                </span>
              </div>
              {/* BL-20260905-84: §13 — the binding/persuasive weight the
                  backend already carries, drawn where the precedent is read. */}
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <PrecedentAuthority attribution={p.attribution} />
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
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
        <span>
          Analysis{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">
            {result.id}
          </code>{' '}
          · {result.latency_ms}ms ·{' '}
          {new Date(result.timestamp).toLocaleString()}
        </span>
        {result.agent_trace[0]?.trace_id && (
          <CopyTraceId traceId={result.agent_trace[0].trace_id} />
        )}
      </div>
    </div>
  )
}

/**
 * The trace id is what a reviewer pastes into the audit store or Phoenix, so
 * it has to leave the page whole — the chip only ever showed the first eight
 * characters, and hand-transcribing the rest from a screenshot is exactly the
 * step people got wrong (BL-20260429-27).
 */
function CopyTraceId({ traceId }: { traceId: string }) {
  const [copied, setCopied] = useState(false)

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(traceId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be denied (insecure origin, permission policy).
      // Say so instead of pretending the copy worked.
      setCopied(false)
    }
  }, [traceId])

  return (
    <span className="inline-flex items-center gap-1.5">
      trace_id{' '}
      <code
        data-testid="trace-id"
        className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300"
      >
        {traceId.slice(0, 8)}…
      </code>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={`Copy trace id ${traceId}`}
        className="rounded px-1.5 py-0.5 text-[11px] text-indigo-300 underline-offset-2 hover:underline focus-ring"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {copied ? 'Trace id copied to clipboard' : ''}
      </span>
    </span>
  )
}

function IracField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mb-1 text-xs uppercase tracking-wider text-slate-400">
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
      <div className="h-4 w-1/3 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
      <div className="h-3 w-full animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
      <div className="h-3 w-5/6 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
      <div className="h-3 w-4/6 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
    </div>
  )
}
