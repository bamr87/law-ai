'use client'

import { fetchProposedTests, type ProposedTest } from '@/lib/api'
import { useEffect, useState } from 'react'

/**
 * The autonomy loop's review queue (BL-20260511-17).
 *
 * `TestSynthesizer` drafts a skip-decorated `*.proposed.py` per thin module
 * and drops it in `backend/tests/autonomy/proposed/`, where until now it was
 * visible only to whoever thought to `ls` inside the container. This lists
 * what is waiting.
 *
 * Deliberately **read-only**: constitution invariants I1 (no auto-merge) and
 * I5 (propose-only) mean a proposal is promoted by a human in a pull request,
 * never by a button on a dashboard. So there is no "accept", no "un-skip" and
 * no "delete" here — only the path to open.
 */
export default function ProposedTestReview() {
  const [files, setFiles] = useState<ProposedTest[] | null>(null)
  const [available, setAvailable] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchProposedTests()
      .then((body) => {
        if (cancelled) return
        setFiles(body.files)
        setAvailable(body.available)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'request failed')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section
      aria-labelledby="proposed-tests-heading"
      data-testid="proposed-test-review"
      className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="proposed-tests-heading"
          className="text-xs font-medium uppercase tracking-wider text-slate-400"
        >
          Proposed tests awaiting review
        </h2>
        {files && files.length > 0 && (
          <span className="text-[11px] text-slate-400">
            {files.length} file{files.length === 1 ? '' : 's'} · skipped until a
            human promotes them
          </span>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-2 text-xs text-red-300">
          Failed to load proposed tests: {error}
        </p>
      )}

      {!error && files && files.length === 0 && (
        <p className="mt-2 text-xs text-slate-400">
          {available
            ? 'No proposed tests pending review.'
            : 'No proposals directory in this checkout.'}
        </p>
      )}

      {!error && files && files.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {files.map((file) => (
            <li
              key={file.path}
              data-testid="proposed-test-row"
              className="rounded-md border border-slate-800 bg-slate-900/40 p-2 text-xs"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-slate-200">{file.name}</span>
                {file.skip_marked ? (
                  <span className="rounded-full bg-slate-700/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-300">
                    skip-marked
                  </span>
                ) : (
                  <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-amber-300">
                    not skipped
                  </span>
                )}
              </div>
              <div className="mt-1 text-slate-400">
                <span className="font-mono">{file.module}</span> ·{' '}
                <span className="font-mono">{file.path}</span> ·{' '}
                {new Date(file.mtime).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
