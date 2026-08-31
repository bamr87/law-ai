'use client'

import { useEffect } from 'react'

/**
 * Module-level error boundary. Keeps the shell alive so a failed panel does
 * not cost the user their navigation — and offers a retry that re-renders the
 * segment instead of forcing a full reload.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Surfaced in the browser console for local debugging; server-side render
    // errors are already reported through Next's own logging.
    console.error(error)
  }, [error])

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-16 sm:px-6">
      <div
        role="alert"
        className="rounded-xl border border-red-500/40 bg-red-500/10 p-6"
      >
        <h1 className="text-lg font-semibold text-red-200">
          This section failed to load
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-red-100/80">
          The rest of the app still works — use the navigation rail to move on,
          or try this section again.
        </p>
        {error.digest && (
          <p className="mt-3 font-mono text-[11px] text-red-200/60">
            digest {error.digest}
          </p>
        )}
        <button
          type="button"
          onClick={reset}
          className="mt-5 rounded-lg border border-red-400/40 bg-red-500/10 px-4 py-2 text-sm font-semibold text-red-100 transition hover:bg-red-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-300"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
