'use client'

import { useShellScroll } from './ShellScroll'
import type { ReactNode } from 'react'

/**
 * The one page frame every route composes.
 *
 * Two jobs, both of them "so no screen has to get this right on its own":
 *
 *  1. A **sticky page header** that condenses once the content scrolls. The
 *     title bar is the answer to "what am I looking at", and the answer must
 *     not scroll away halfway down a 40-run audit trail.
 *  2. A **measured body container** so every module lines up on the same
 *     gutter and reading width instead of six hand-rolled `max-w-*`s.
 *
 * `scripts/ux_audit.py` fails the build on a page under `app/(app)` that
 * renders neither this nor an explicit, justified bare-page opt-out.
 */

export type PageWidth = 'wide' | 'roomy' | 'regular' | 'narrow'

/**
 * Page measures, in two or three steps.
 *
 * The shell eats a fixed 36.5rem of the viewport whenever both side panels
 * are docked (rail 3.5 + sidebar 14 + inspector 19), so below roughly 1900px
 * the caps here never bind — the content column is already narrower than
 * `max-w-7xl` and the page fills it. The extra steps are what a large
 * monitor actually gets: at 2560px a `wide` page now runs to 1760px of the
 * 1976px available instead of stopping at 1280 and leaving a 350px dead
 * gutter down each side.
 *
 * Reading-first widths grow far less, and `narrow` not at all: a settings
 * form at 1600px is not a better settings form. Anything whose job is prose
 * caps its own measure inside the container (the library reader holds ~70ch)
 * — the page frame's job is to stop wasting the screen, not to stretch text.
 */
const WIDTH: Record<PageWidth, string> = {
  wide: 'max-w-7xl min-[1800px]:max-w-[96rem] min-[2200px]:max-w-[110rem]',
  roomy: 'max-w-6xl min-[1800px]:max-w-[84rem] min-[2200px]:max-w-[96rem]',
  regular: 'max-w-5xl min-[1800px]:max-w-6xl',
  narrow: 'max-w-3xl',
}

export type PageAccent = 'blue' | 'indigo' | 'emerald' | 'amber' | 'slate'

const ACCENT: Record<PageAccent, { dot: string; text: string }> = {
  blue: { dot: 'bg-blue-400', text: 'text-slate-500' },
  indigo: { dot: 'bg-indigo-400', text: 'text-indigo-400/80' },
  emerald: { dot: 'bg-emerald-400', text: 'text-emerald-400/80' },
  amber: { dot: 'bg-amber-400', text: 'text-amber-400/80' },
  slate: { dot: 'bg-slate-400', text: 'text-slate-500' },
}

export default function PageLayout({
  eyebrow,
  title,
  description,
  actions,
  accent = 'blue',
  width = 'wide',
  children,
}: {
  eyebrow: string
  title: string
  description?: ReactNode
  /** Buttons that belong to the page, not to a panel inside it. */
  actions?: ReactNode
  accent?: PageAccent
  width?: PageWidth
  children: ReactNode
}) {
  const { scrolled } = useShellScroll()
  const tone = ACCENT[accent]
  const container = `mx-auto w-full ${WIDTH[width]} px-4 sm:px-6 min-[1800px]:px-10`

  return (
    <div className="flex min-h-full flex-col">
      <header
        data-testid="page-header"
        data-condensed={scrolled ? 'true' : 'false'}
        className={
          'shell-sticky-header shell-motion border-b bg-slate-950/85 backdrop-blur transition-[padding,border-color] duration-200 ' +
          (scrolled ? 'border-slate-800' : 'border-transparent')
        }
      >
        <div
          className={
            container +
            ' flex items-center justify-between gap-4 transition-[padding] duration-200 ' +
            (scrolled ? 'py-2.5' : 'py-6')
          }
        >
          <div className="min-w-0">
            {/* The eyebrow and description are the first things to go: once
             * condensed the header is a locator, not an introduction. */}
            <div
              className={
                'flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] transition-all duration-200 ' +
                tone.text +
                (scrolled
                  ? ' h-0 overflow-hidden opacity-0'
                  : ' mb-1.5 opacity-100')
              }
              aria-hidden={scrolled}
            >
              <span
                className={'inline-block h-1.5 w-1.5 rounded-full ' + tone.dot}
              />
              {eyebrow}
            </div>
            <h1
              className={
                'truncate font-bold tracking-tight text-slate-100 transition-all duration-200 ' +
                (scrolled ? 'text-base' : 'text-3xl sm:text-4xl')
              }
            >
              {title}
            </h1>
            {description && (
              <div
                className={
                  'max-w-3xl text-sm leading-relaxed text-slate-400 transition-all duration-200 ' +
                  (scrolled
                    ? 'h-0 overflow-hidden opacity-0'
                    : 'mt-2 opacity-100')
                }
                aria-hidden={scrolled}
              >
                {description}
              </div>
            )}
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </div>
      </header>

      <div className={container + ' flex-1 pb-16 pt-6'}>{children}</div>
    </div>
  )
}

/**
 * A control bar that pins itself directly under the page header.
 *
 * Use for filters, tabs, and run controls — the things a user reaches for
 * repeatedly while reading a long region. It parks against
 * `--shell-pageheader-h`, so the offset stays correct if the header's
 * condensed height ever changes.
 */
export function StickyToolbar({
  children,
  className = '',
  label,
}: {
  children: ReactNode
  className?: string
  /** Names the region for screen readers; omit only for pure decoration. */
  label?: string
}) {
  return (
    <div
      role={label ? 'region' : undefined}
      aria-label={label}
      data-testid="sticky-toolbar"
      className={
        // Negative margins that match the container's gutter at every step of
        // it: the bar bleeds to the edge of the page frame, so a gutter that
        // grows on a large monitor has to grow here too or the toolbar stops
        // short of its own page.
        'shell-sticky-sub -mx-4 border-y border-slate-800/80 bg-slate-950/85 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6 min-[1800px]:-mx-10 min-[1800px]:px-10 ' +
        className
      }
    >
      {children}
    </div>
  )
}
