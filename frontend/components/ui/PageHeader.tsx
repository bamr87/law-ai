import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** Standard page eyebrow + title + description block (was copy-pasted per route). */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-end justify-between gap-4',
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-brand">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand" />
            {eyebrow}
          </div>
        )}
        <h1 className="text-3xl font-bold tracking-tight text-ink">{title}</h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p>
        )}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  )
}
