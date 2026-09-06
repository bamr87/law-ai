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

import {
  askLsatTutor,
  type LsatChoiceLabel,
  type LsatTutorResponse,
} from '@/lib/api'

export default function TutorPane({
  questionId,
  userChoice,
  initialQuestion,
}: {
  questionId: string
  userChoice: LsatChoiceLabel | null
  /** Spec 045 FR-8: canned opener, e.g. a no-spoiler walkthrough request. */
  initialQuestion?: string
}) {
  const [followUp, setFollowUp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<LsatTutorResponse | null>(null)

  const ask = useCallback(
    async (overrideQuestion?: string, refresh = false) => {
      setLoading(true)
      setError(null)
      try {
        const r = await askLsatTutor({
          question_id: questionId,
          user_choice: userChoice,
          user_question: overrideQuestion ?? followUp ?? null,
          // Spec 045 FR-13: identical requests serve the saved walkthrough;
          // refresh forces a fresh model call.
          refresh,
        })
        setResponse(r)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Tutor failed')
      } finally {
        setLoading(false)
      }
    },
    [questionId, userChoice, followUp],
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

      {loading && (
        <div className="mt-3 animate-pulse space-y-2">
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
