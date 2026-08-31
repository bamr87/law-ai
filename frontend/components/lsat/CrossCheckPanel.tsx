'use client'

import { useState } from 'react'

import { crossCheckLsat, type LsatCrossCheck } from '@/lib/api'

/**
 * Post-grade answer verification (spec 041 FR-14).
 *
 * On demand, the provider chain re-solves the question blind (no answer
 * key in the prompt) and the panel reports whether the independent pick
 * agrees with the bank's key. Agreement is labelled as corroboration by a
 * named model — never as proof (constitution §13); disagreement is flagged
 * for human review. Verdicts are cached server-side, so re-checking a
 * question is free after the first run.
 */
export default function CrossCheckPanel({ questionId }: { questionId: string }) {
  const [result, setResult] = useState<LsatCrossCheck | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      setResult(await crossCheckLsat(questionId, { refresh }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cross-check failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-3">
      {!result && (
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-40"
        >
          {loading ? 'Cross-checking…' : '🔍 Cross-check this answer'}
        </button>
      )}

      {error && (
        <p className="mt-2 text-sm text-red-300" role="alert">
          {error}
          <button
            type="button"
            onClick={() => void run()}
            className="ml-2 underline hover:text-red-200"
          >
            Retry
          </button>
        </p>
      )}

      {result && (
        <div
          className={
            'rounded-lg border p-3 text-sm ' +
            (result.agree === true
              ? 'border-emerald-500/40 bg-emerald-500/5'
              : result.agree === false
                ? 'border-amber-500/50 bg-amber-500/10'
                : 'border-slate-700 bg-slate-950/40')
          }
        >
          <p className="flex flex-wrap items-center gap-2">
            {result.agree === true && (
              <span className="font-semibold text-emerald-300">
                ✓ Independent solve agrees with the answer key
              </span>
            )}
            {result.agree === false && (
              <span className="font-semibold text-amber-300" role="alert">
                ⚠ Disagreement — flagged for human review
              </span>
            )}
            {result.agree === null && (
              <span className="text-slate-400">
                Cross-check unavailable — no model reachable.
              </span>
            )}
            {result.cached && (
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400">
                saved verdict
              </span>
            )}
          </p>
          {result.model_choice !== null && (
            <p className="mt-1 text-xs text-slate-400">
              Blind solve picked{' '}
              <span className="font-mono text-slate-200">
                {result.model_choice}
              </span>
              ; the answer key is{' '}
              <span className="font-mono text-slate-200">
                {result.bank_choice}
              </span>
              . One model&apos;s solve is corroboration, not proof.
            </p>
          )}
          {result.used_llm && result.rationale && (
            <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-slate-400">
              {result.rationale}
            </p>
          )}
          <p className="mt-2 flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-wider text-slate-500">
            <span>{result.used_llm ? result.model : 'offline'}</span>
            <button
              type="button"
              onClick={() => void run(true)}
              disabled={loading}
              className="underline hover:text-slate-300 disabled:opacity-40"
            >
              {loading ? 'Re-checking…' : 'Re-run fresh'}
            </button>
          </p>
        </div>
      )}
    </div>
  )
}
