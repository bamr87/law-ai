'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'

/**
 * The "Improve this page" widget — one floating button that turns what a user
 * is looking at into a well-formed GitHub issue against this repo, carrying the
 * route, the environment, and the console/error lines that led up to the
 * report (spec: bamr87/bamr87 `specs/FEEDBACK.md`, UPS-FB).
 *
 * The widget itself is `public/fleet-feedback.js`, vendored from the fleet kit
 * and shared with every other repo in the fleet, so an issue filed here is
 * byte-identical to one filed from a Jekyll page — same sections, same labels,
 * same `<!-- fleet-feedback v1 -->` marker the issue pipeline reads. It renders
 * in a shadow root and reads the `--fleet-*` tokens mapped in `ui/base.css`.
 *
 * Mounted ONCE in the root layout rather than in `AppShell`, deliberately: the
 * 404 route and the error boundary live outside the shell, and those are the
 * two pages a user most wants to report from.
 *
 * Filing is `url` mode — the widget opens a prefilled `issues/new` form and the
 * user submits it under their own GitHub account. No token exists in the
 * browser or on the server, and reports stay attributable and rate-limited to a
 * real account. `proxy` mode is deliberately not enabled here; see the PR notes.
 */

const REPO = process.env.NEXT_PUBLIC_FEEDBACK_REPO || 'bamr87/law-ai'
const BRANCH = process.env.NEXT_PUBLIC_FEEDBACK_BRANCH || 'main'

export interface OpenFeedbackOptions {
  /** Taxonomy id — 'fix-page', 'improve-page', 'accessibility', 'performance', … */
  type?: string
  /** Pre-fills the textarea; the user can still edit it before filing. */
  description?: string
  /** Appended to the description — an error stack, the route that 404'd. */
  extra?: string
}

interface FleetFeedbackApi {
  open: (o?: OpenFeedbackOptions) => void
  close: () => void
  breadcrumb: (level: string, message: string) => void
  version: string
}

function api(): FleetFeedbackApi | undefined {
  return typeof window === 'undefined'
    ? undefined
    : (window as unknown as { FleetFeedback?: FleetFeedbackApi }).FleetFeedback
}

/**
 * Open the dialog from anywhere — the error boundary, the 404 route, a
 * "suggest an edit" link. A no-op when the widget has not loaded, so a caller
 * never has to guard.
 */
export function openFeedback(opts?: OpenFeedbackOptions): void {
  api()?.open(opts)
}

/**
 * Record one line in the capture buffer. `lib/api.ts` calls this on a failed
 * request so a report carries the API call that actually broke, rather than
 * only the exception the UI surfaced.
 */
export function breadcrumb(level: string, message: string): void {
  const w = window as unknown as {
    __fleetFeedback?: { breadcrumb?: (l: string, m: string) => void }
  }
  w.__fleetFeedback?.breadcrumb?.(level, message)
}

/* React 19 removed the global JSX namespace; augmenting `react` is the form
 * that compiles under both 18 and 19. */
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'fleet-feedback': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      > &
        Record<string, string | undefined>
    }
  }
}

export default function FeedbackButton() {
  const pathname = usePathname() || '/'

  useEffect(() => {
    if (document.querySelector('script[src="/fleet-feedback.js"]')) return
    const s = document.createElement('script')
    s.src = '/fleet-feedback.js'
    s.async = true
    document.head.appendChild(s)
  }, [])

  return (
    <fleet-feedback
      repo={REPO}
      branch={BRANCH}
      route={pathname}
      labels="page-feedback"
      assignee="copilot"
      label="Improve this page"
      env={process.env.NODE_ENV}
    />
  )
}
