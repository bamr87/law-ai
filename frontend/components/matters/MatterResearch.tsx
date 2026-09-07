'use client'

import { useCallback, useState } from 'react'

import { runAnalysis, type AnalysisResponse } from '@/lib/api'

/**
 * Research a question *inside* a matter (BL-20260906-95).
 *
 * `POST /api/analysis` has accepted an owner-checked `matter_id` since
 * BL-20260817-05 — the server promotes the authorities this matter has already
 * had verified, so a later round ranks known-good citations first — but no UI
 * ever sent one, so the boost could not be reached from the product. This is
 * that entry point: the run is scoped to the matter on screen, and the reply
 * says out loud when the ordering was biased, because a promoted passage is a
 * deliberate deviation from the corpus's own ranking.
 *
 * Deliberately not a second Analysis Studio: it shows the issue, the
 * conclusion and the boost, and leaves the full trace to `/analysis`.
 */
export default function MatterResearch({
  matterId,
  jurisdiction,
}: {
  matterId: number
  /** The matter's jurisdiction, forwarded so the run is filtered like it. */
  jurisdiction?: string
}) {
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)

  const run = useCallback(async () => {
    const question = text.trim()
    if (!question || running) return
    setRunning(true)
    setError(null)
    try {
      setResult(
        await runAnalysis({
          text: question,
          matter_id: matterId,
          ...(jurisdiction ? { jurisdiction } : {}),
        }),
      )
    } catch {
      // The server answers 404 for a matter the caller does not own, which is
      // the same answer as "no such matter" on purpose — so say neither.
      setError('That research round could not be run. Try again.')
      setResult(null)
    } finally {
      setRunning(false)
    }
  }, [jurisdiction, matterId, running, text])

  const boosted = result?.irac.retrieval?.boosted_count ?? 0

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Research in this matter
      </h3>
      <p className="mt-1 text-xs text-slate-400">
        The run is scoped to this matter, so authorities you have already
        verified here are ranked first.
      </p>
      <label
        className="mt-3 block text-xs text-slate-400"
        htmlFor="matter-research"
      >
        Question or fact pattern
      </label>
      <textarea
        id="matter-research"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={3}
        className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-200"
      />
      <button
        type="button"
        onClick={run}
        disabled={running || text.trim().length === 0}
        className="mt-3 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-amber-400 disabled:opacity-50"
      >
        {running ? 'Researching…' : 'Research'}
      </button>

      {error && (
        <p role="status" className="mt-3 text-xs text-amber-300">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 space-y-2 border-t border-slate-800 pt-3 text-sm">
          <p className="text-slate-200">{result.irac.issue}</p>
          <p className="text-slate-300">{result.irac.conclusion}</p>
          {boosted > 0 && (
            <p
              data-testid="matter-research-boost"
              className="text-xs text-indigo-300"
            >
              {boosted} passage(s) promoted because{' '}
              {result.irac.retrieval?.boost_source || 'this matter'} had already
              verified them — this order is not the corpus&rsquo;s own.
            </p>
          )}
          {result.requires_human_review && (
            <p className="text-xs text-amber-300">
              Low confidence — a human should review this before it is used.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
