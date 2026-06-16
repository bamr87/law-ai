import { AlertTriangle, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** Indeterminate spinner. */
export function Spinner({ className }: { className?: string }) {
  return (
    <Loader2
      className={cn('h-4 w-4 animate-spin text-muted', className)}
      aria-hidden
    />
  )
}

/** Shimmer placeholder lines while a panel loads. */
export function SkeletonLines({
  rows = 3,
  className,
}: {
  rows?: number
  className?: string
}) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-8 animate-pulse rounded-md bg-surface-3/60"
          style={{ animationDelay: `${i * 90}ms` }}
        />
      ))}
    </div>
  )
}

/** Single shimmer block of arbitrary height. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-surface-3/60', className)}
      aria-hidden
    />
  )
}

/** Inline error with optional retry. */
export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <span className="break-words">{message}</span>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="ml-2 inline font-medium underline underline-offset-2 hover:text-ink"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

/** Empty-state placeholder with optional icon + action. */
export function EmptyState({
  message,
  icon,
  action,
  className,
}: {
  message: ReactNode
  icon?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-center text-xs text-muted',
        className,
      )}
    >
      {icon && <span className="text-subtle">{icon}</span>}
      <div className="text-balance">{message}</div>
      {action}
    </div>
  )
}
