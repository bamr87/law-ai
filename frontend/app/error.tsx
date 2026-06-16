'use client'

import { AlertTriangle, RotateCw } from 'lucide-react'
import { useEffect } from 'react'
import { Button } from '@/components/ui'

/** Route-level error boundary — a client crash degrades to this, not a white screen. */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('Route error boundary:', error)
  }, [error])

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/15 text-danger">
        <AlertTriangle className="h-6 w-6" aria-hidden />
      </div>
      <div>
        <h1 className="text-lg font-semibold text-ink">Something went wrong</h1>
        <p className="mt-1 text-sm text-muted">
          This view hit an unexpected error. Your data is safe — try reloading
          the section.
        </p>
        {error.digest && (
          <p className="mt-2 font-mono text-[11px] text-subtle">
            ref: {error.digest}
          </p>
        )}
      </div>
      <Button onClick={reset} icon={<RotateCw className="h-4 w-4" />}>
        Try again
      </Button>
    </main>
  )
}
