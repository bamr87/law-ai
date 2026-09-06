'use client'

/**
 * AI Tutor pane — coaching for one question, with follow-up questions.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — the tutor is a model call through the provider chain
 * (`/api/lsat/tutor`), which the serverless static export cannot make. Its
 * offline surface is the solve guide, which both products share.
 */

import { useCallback, useEffect, useState } from 'react'

import { newStreamId, openAgentStream } from '@/lib/agentStream'
import {
  askLsatTutor,
  type LsatChoiceLabel,
  type LsatTutorResponse,
  type LsatTutorTrace,
} from '@/lib/api'

export default function TutorPane({
  questionId,
  userChoice,
  initialQuestion,
  trace,
}: {
  questionId: string
  userChoice: LsatChoiceLabel | null
  /** Spec 045 FR-8: canned opener, e.g. a no-spoiler walkthrough request. */
  initialQuestion?: string
  /**
   * What the learner did on this attempt (BL-20260429-18) — hints revealed,
   * time spent. Read at ask time from the card's refs, so it reflects the
   * attempt being asked about rather than the render that mounted this pane.
   */
  trace?: () => LsatTutorTrace
}) {
  const [followUp, setFollowUp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<LsatTutorResponse | null>(null)
  // BL-20260503-03: coaching rendered as the model writes it. Strictly an
  // enhancement — the REST body below is still the authoritative walkthrough,
  // and everything here is discarded once it lands.
  const [liveText, setLiveText] = useState('')

  const ask = useCallback(
    async (overrideQuestion?: string, refresh = false) => {
      setLoading(true)
      setError(null)
      setLiveText('')

      // Subscribe BEFORE posting (spec 032): the group membership has to
      // exist before the server starts emitting, or the deltas land nowhere.
      // A socket failure is not an error — the request runs unstreamed and
      // the learner waits, exactly as before.
      const streamId = newStreamId()
      let socket: WebSocket | null = null
      try {
        socket = await openAgentStream(streamId, (event) => {
          if (event.type === 'tutor_token') {
            setLiveText((prev) => prev + event.text)
          } else if (event.type === 'tutor_step' && event.stage === 'interrupted') {
            // A half-written answer must not read as the answer; the offline
            // fallback in the REST body replaces it.
            setLiveText('')
          }
        })
      } catch {
        socket = null
      }

      try {
        const r = await askLsatTutor({
          question_id: questionId,
          user_choice: userChoice,
          user_question: overrideQuestion ?? followUp ?? null,
          // Spec 045 FR-13: identical requests serve the saved walkthrough;
          // refresh forces a fresh model call.
          refresh,
          ...(trace ? { trace: trace() } : {}),
          ...(socket ? { stream_id: streamId, stream_tokens: true } : {}),
        })
        setResponse(r)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Tutor failed')
      } finally {
        socket?.close()
        setLiveText('')
        setLoading(false)
      }
    },
    [questionId, userChoice, followUp, trace],
  )

  // Auto-fire the first call when the pane opens with no follow-up so the
  // learner sees coaching immediately.
  useEffect(() => {
    if (!response && !loading) void ask(initialQuestion ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/[0.03] p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-wider text-amber-300">
          AI Tutor
        </div>
        {response && (
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500">
            {response.cached && (
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
                saved walkthrough
              </span>
            )}
            <span>
              {response.used_llm ? response.model : 'offline fallback'} ·{' '}
              {Math.round(response.confidence * 100)}% conf
              {!response.cached && <> · {Math.round(response.latency_ms)}ms</>}
            </span>
            {/* BL-20260503-06: the same deep link the analysis path has had
              * since BL-20260502-05. Rendered only when a collector is
              * configured — the local-first default is no telemetry, and a
              * link to a trace that was never exported is worse than none.
              * `langgraph_thread_id` is on the response for contract parity
              * but is always null here — the tutor calls the provider chain
              * directly and runs no graph — so there is nothing to render
              * beside the link. */}
            {response.phoenix_trace_url && (
              <a
                href={response.phoenix_trace_url}
                target="_blank"
                rel="noreferrer"
                title={response.trace_id ?? undefined}
                className="text-blue-300 underline-offset-2 hover:underline"
              >
                Phoenix trace
              </a>
            )}
            {response.cached && (
              <button
                type="button"
                onClick={() => void ask(undefined, true)}
                disabled={loading}
                className="underline hover:text-slate-300 disabled:opacity-40"
              >
                Regenerate
              </button>
            )}
          </div>
        )}
      </div>

      {loading && liveText && (
        <p
          className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-200"
          aria-live="polite"
        >
          {liveText}
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-amber-300/70 align-text-bottom motion-reduce:animate-none" />
        </p>
      )}

      {loading && !liveText && (
        <div className="mt-3 animate-pulse space-y-2 motion-reduce:animate-none">
          <div className="h-3 w-3/4 rounded bg-slate-800" />
          <div className="h-3 w-2/3 rounded bg-slate-800" />
          <div className="h-3 w-1/2 rounded bg-slate-800" />
        </div>
      )}

      {error && !loading && (
        <p className="mt-2 text-sm text-red-300" role="alert">
          {error}
          <button
            onClick={() => void ask()}
            className="ml-2 underline hover:text-red-200"
          >
            Retry
          </button>
        </p>
      )}

      {response && !loading && (
        <>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-200">
            {response.coaching}
          </p>
          {response.next_steps.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Next steps
              </div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-300">
                {response.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {response.concepts.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Concepts in play
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {response.concepts.map((c) => (
                  <span
                    key={c.id}
                    title={c.summary}
                    className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-200"
                  >
                    {c.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          type="text"
          aria-label="Ask the tutor a follow-up question"
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          placeholder="Ask a follow-up — e.g. 'Why is C wrong?'"
          className="min-w-[260px] flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-500 focus-ring-practice"
        />
        <button
          onClick={() => void ask()}
          disabled={loading}
          className="rounded-md bg-amber-500/80 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-40"
        >
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>
    </div>
  )
}
