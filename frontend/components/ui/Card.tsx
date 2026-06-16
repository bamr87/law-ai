import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { ErrorState, SkeletonLines } from './feedback'

/** Bare surface card — the canonical chrome the audit found duplicated 33×. */
export function Card({
  className,
  children,
  interactive = false,
}: {
  className?: string
  children: ReactNode
  interactive?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-surface/70 shadow-[var(--shadow-card)] backdrop-blur',
        interactive &&
          'transition hover:border-border-strong hover:bg-surface',
        className,
      )}
    >
      {children}
    </div>
  )
}

export interface PanelProps {
  title?: ReactNode
  subtitle?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  loading?: boolean
  error?: string | null
  className?: string
  bodyClassName?: string
  children: ReactNode
}

/**
 * A Card with a standard header (title/subtitle/actions) and built-in
 * loading + error states, so every dashboard panel stops re-implementing them.
 */
export function Panel({
  title,
  subtitle,
  icon,
  actions,
  loading = false,
  error = null,
  className,
  bodyClassName,
  children,
}: PanelProps) {
  return (
    <section
      className={cn(
        'rounded-xl border border-border bg-surface/70 p-4 shadow-[var(--shadow-card)] backdrop-blur',
        className,
      )}
    >
      {(title || actions) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            {icon && <span className="mt-0.5 text-muted">{icon}</span>}
            <div className="min-w-0">
              {title && (
                <h2 className="text-base font-semibold text-ink">{title}</h2>
              )}
              {subtitle && (
                <p className="mt-0.5 text-xs text-muted">{subtitle}</p>
              )}
            </div>
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      {loading ? (
        <SkeletonLines />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <div className={bodyClassName}>{children}</div>
      )}
    </section>
  )
}
