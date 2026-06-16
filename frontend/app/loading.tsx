import { Spinner } from '@/components/ui'

/** Route-level loading fallback shown during navigation/Suspense. */
export default function RouteLoading() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-7xl items-center justify-center px-6">
      <div className="flex items-center gap-3 text-sm text-muted">
        <Spinner className="h-5 w-5" />
        Loading…
      </div>
    </main>
  )
}
