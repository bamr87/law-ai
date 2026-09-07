/**
 * The feedback widget's integration surface.
 *
 * The widget itself (public/fleet-feedback.js) is vendored from the fleet kit
 * and covered by that kit's own 25 contract tests — the issue body, labels,
 * escaping and URL budget are locked there, once, for every repo that vendors
 * it. What this file covers is the half that is ours: that the element is
 * mounted with the attributes it needs to file against the right repo and
 * route, and that the three call sites which hand it context — the error
 * boundary, the 404 route, and the API client — actually reach it.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FeedbackButton, {
  breadcrumb,
  openFeedback,
} from '@/components/shell/FeedbackButton'
import NotFoundReportLink from '@/components/shell/NotFoundReportLink'

vi.mock('next/navigation', () => ({
  usePathname: () => '/analysis',
}))

describe('FeedbackButton', () => {
  beforeEach(() => {
    document.head.querySelectorAll('script[src="/fleet-feedback.js"]').forEach((s) => s.remove())
    delete (window as unknown as Record<string, unknown>).FleetFeedback
    delete (window as unknown as Record<string, unknown>).__fleetFeedback
  })

  it('mounts the element with the repo, branch and current route', () => {
    const { container } = render(<FeedbackButton />)
    const el = container.querySelector('fleet-feedback')

    expect(el).not.toBeNull()
    // Without a repo the widget has nowhere to file, and fails at submit time
    // rather than at mount — so it is worth asserting here.
    expect(el?.getAttribute('repo')).toBe('bamr87/law-ai')
    expect(el?.getAttribute('branch')).toBe('main')
    // Pages here are routes, not files, so `route` is what identifies them.
    expect(el?.getAttribute('route')).toBe('/analysis')
    expect(el?.getAttribute('labels')).toBe('page-feedback')
  })

  it('loads the vendored widget exactly once, however many times it renders', () => {
    render(<FeedbackButton />)
    render(<FeedbackButton />)
    expect(
      document.head.querySelectorAll('script[src="/fleet-feedback.js"]'),
    ).toHaveLength(1)
  })

  it('openFeedback and breadcrumb are no-ops until the widget has loaded', () => {
    // Every call site fires on a failure path. If these threw when the script
    // had not arrived yet, reporting an error would itself error.
    expect(() => openFeedback({ type: 'fix-page' })).not.toThrow()
    expect(() => breadcrumb('net', 'GET /api/x → 502')).not.toThrow()
  })

  it('openFeedback forwards the type and context to the widget', () => {
    const open = vi.fn()
    ;(window as unknown as Record<string, unknown>).FleetFeedback = { open }

    openFeedback({ type: 'fix-page', extra: 'Missing route: /nope' })

    expect(open).toHaveBeenCalledWith({
      type: 'fix-page',
      extra: 'Missing route: /nope',
    })
  })

  it('breadcrumb reaches the capture buffer', () => {
    const push = vi.fn()
    ;(window as unknown as Record<string, unknown>).__fleetFeedback = {
      breadcrumb: push,
    }

    breadcrumb('net', 'POST /api/analysis → 502 (1243ms)')

    expect(push).toHaveBeenCalledWith('net', 'POST /api/analysis → 502 (1243ms)')
  })
})

describe('NotFoundReportLink', () => {
  it('hands the route that 404ed to the widget, pre-typed', async () => {
    const open = vi.fn()
    ;(window as unknown as Record<string, unknown>).FleetFeedback = { open }

    render(<NotFoundReportLink />)
    screen.getByRole('button', { name: /report this link/i }).click()

    expect(open).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'fix-page',
        // The route is the one thing this page knows and the widget does not.
        description: expect.stringContaining('/analysis'),
      }),
    )
  })
})
