import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { type Tone, toneChip, toneDot } from './tokens'

export interface BadgeProps {
  tone?: Tone
  children: ReactNode
  /** Show a leading status dot. */
  dot?: boolean
  /** Pulse the dot (e.g. "live"). */
  pulse?: boolean
  className?: string
  title?: string
  uppercase?: boolean
}

export function Badge({
  tone = 'neutral',
  children,
  dot = false,
  pulse = false,
  className,
  title,
  uppercase = false,
}: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        uppercase && 'uppercase tracking-wide',
        toneChip[tone],
        className,
      )}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && (
            <span
              className={cn(
                'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
                toneDot[tone],
              )}
            />
          )}
          <span
            className={cn(
              'relative inline-flex h-1.5 w-1.5 rounded-full',
              toneDot[tone],
            )}
          />
        </span>
      )}
      {children}
    </span>
  )
}
