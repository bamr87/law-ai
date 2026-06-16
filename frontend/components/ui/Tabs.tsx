'use client'

import { type ReactNode, useRef } from 'react'
import { cn } from '@/lib/cn'

export interface TabItem {
  id: string
  label: ReactNode
  count?: number
  icon?: ReactNode
}

/**
 * Accessible tablist implementing the WAI-ARIA roving-tabindex pattern
 * (arrow keys move between tabs, only the active tab is in the tab order).
 */
export function Tabs({
  items,
  active,
  onChange,
  className,
  'aria-label': ariaLabel = 'Sections',
}: {
  items: TabItem[]
  active: string
  onChange: (id: string) => void
  className?: string
  'aria-label'?: string
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  const onKeyDown = (e: React.KeyboardEvent, idx: number) => {
    let next = idx
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % items.length
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
      next = (idx - 1 + items.length) % items.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = items.length - 1
    else return
    e.preventDefault()
    onChange(items[next].id)
    refs.current[next]?.focus()
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        'flex flex-wrap gap-1 rounded-xl border border-border bg-surface/60 p-1',
        className,
      )}
    >
      {items.map((item, idx) => {
        const selected = item.id === active
        return (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[idx] = el
            }}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(e) => onKeyDown(e, idx)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition',
              selected
                ? 'bg-brand/15 text-brand ring-1 ring-inset ring-brand/30'
                : 'text-muted hover:bg-surface-2 hover:text-ink',
            )}
          >
            {item.icon}
            {item.label}
            {item.count !== undefined && (
              <span className="text-xs opacity-60">{item.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
