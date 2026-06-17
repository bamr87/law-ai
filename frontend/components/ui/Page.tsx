import type { ReactNode } from 'react'
import Link from 'next/link'
import { cn } from '@/lib/cn'

export interface PageLink {
  href: string
  label: ReactNode
}

/**
 * Standard page shell matching the EDGAR organization format: a skip-link, a
 * header (eyebrow + h1 + tagline + optional context note + inline sub-nav
 * links + actions), then the page body. Every route renders through this so
 * navigation and structure are identical across the suite.
 */
export function Page({
  eyebrow,
  title,
  tagline,
  note,
  links,
  actions,
  children,
  contentId = 'main-content',
  className,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  tagline?: ReactNode
  note?: ReactNode
  links?: PageLink[]
  actions?: ReactNode
  children: ReactNode
  contentId?: string
  className?: string
}) {
  return (
    <div className={cn('mx-auto w-full max-w-[1100px] px-4 pb-12 pt-5 sm:px-6', className)}>
      <a
        href={`#${contentId}`}
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-md focus:bg-brand focus:px-3 focus:py-1.5 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      <header className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {eyebrow && (
              <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand" />
                {eyebrow}
              </div>
            )}
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[1.65rem]">
              {title}
            </h1>
            {tagline && (
              <p className="mt-1.5 max-w-[62ch] text-sm leading-relaxed text-muted">
                {tagline}
              </p>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>

        {note && (
          <aside
            role="note"
            className="mt-3 rounded-lg border border-border bg-surface-2 px-4 py-2.5 text-sm leading-relaxed text-muted"
          >
            {note}
          </aside>
        )}

        {links && links.length > 0 && (
          <nav className="mt-3 flex flex-wrap gap-4 text-sm" aria-label="Section">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="font-semibold text-brand underline-offset-2 hover:underline"
              >
                {l.label}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main id={contentId} className="flex flex-col gap-5">
        {children}
      </main>
    </div>
  )
}
