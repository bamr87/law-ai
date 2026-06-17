import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * EDGAR `.settings-disclosure` — a native `<details>` collapsible with a
 * rotating chevron, used for secondary settings/advanced content at the
 * bottom of a page.
 */
export function Disclosure({
  summary,
  children,
  defaultOpen = false,
  className,
}: {
  summary: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  return (
    <details
      open={defaultOpen}
      className={cn(
        'group overflow-hidden rounded-xl border border-border bg-surface-2',
        className,
      )}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-2.5 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 rotate-45 border-b-2 border-r-2 border-muted transition group-open:rotate-[225deg]"
        />
        {summary}
      </summary>
      <div className="border-t border-border px-4 py-3.5">{children}</div>
    </details>
  )
}
