/**
 * Route-level loading state for every module.
 *
 * The shell stays mounted across this — masthead, rail, and panels do not
 * blink — so navigation reads as "this pane is loading", not "the app went
 * away".
 */
export default function AppLoading() {
  return (
    <div
      className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6"
      aria-busy="true"
    >
      <p className="sr-only" role="status">
        Loading…
      </p>
      <div className="h-8 w-64 animate-pulse rounded-md bg-slate-800/70" />
      <div className="mt-3 h-4 w-96 max-w-full animate-pulse rounded bg-slate-900" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-xl border border-slate-800 bg-slate-900/40"
          />
        ))}
      </div>
    </div>
  )
}
