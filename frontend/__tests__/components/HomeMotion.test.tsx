/**
 * BL-20260831-03 — `prefers-reduced-motion` on the homepage.
 *
 * Spec 041 gated smooth scrolling and shell transitions, but the decorative
 * "live" pulses on the dashboard kept animating for anyone who had asked the
 * OS to stop. Tailwind's `motion-reduce:` variant compiles to a
 * `prefers-reduced-motion: reduce` media query, and jsdom applies no CSS, so
 * the assertion is on the class the browser needs rather than on a computed
 * style.
 *
 * (The Cytoscape half of the item was already safe: GraphViewer runs its
 * layout with `animate: false`, asserted here so a future layout change has
 * to notice.)
 */
import AppLoading from '@/app/(app)/loading'
import Home from '@/app/(app)/page'
import HomeStats from '@/components/HomeStats'
import { SkeletonGrid, SkeletonQuestion } from '@/components/lsat/LabPrimitives'
import { server } from '@/mocks/server'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

const BASE = 'http://localhost:8000'

beforeEach(() => {
  server.use(
    http.get(`${BASE}/api/agents`, () =>
      HttpResponse.json({ count: 2, agents: [] }),
    ),
    http.get(`${BASE}/api/agents/backlog`, () =>
      HttpResponse.json({
        counts: { open: 1, claimed: 0, done: 4, total: 5 },
        open: [],
        claimed: [],
        done: [],
      }),
    ),
    http.get(`${BASE}/api/agents/specs`, () =>
      HttpResponse.json({
        count: 1,
        specs: [{ id: '041-shell-navigation-scroll', status: 'shipped' }],
      }),
    ),
  )
})

/**
 * Every element carrying an *unconditional* animation utility — a bare
 * `animate-*` token, ignoring variant-prefixed ones like
 * `motion-reduce:animate-none`.
 */
function animated(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll('[class*="animate-"]')).filter(
    (el) =>
      Array.from(el.classList).some(
        (token) => token.startsWith('animate-') && token !== 'animate-none',
      ),
  )
}

describe('homepage reduced motion (BL-20260831-03)', () => {
  it('pairs every hero animation with motion-reduce:animate-none', () => {
    const { container } = render(<Home />)
    const moving = animated(container)
    expect(moving.length).toBeGreaterThan(0)
    for (const el of moving) {
      expect(el.className).toContain('motion-reduce:animate-none')
    }
  })

  it('gates the route loading skeletons too', () => {
    // `app/(app)/loading.tsx` is the fallback React paints *at the homepage
    // route* (and at every module under it) while a page streams in, so a
    // pulse left ungated here animates on the homepage for a reader who asked
    // the OS to stop — the clause is about the route, not one component.
    const { container } = render(<AppLoading />)
    const moving = animated(container)
    expect(moving.length).toBeGreaterThan(0)
    for (const el of moving) {
      expect(el.className).toContain('motion-reduce:animate-none')
    }
  })

  it('gates the shared LSAT skeletons', () => {
    // The residual pulses the homepage pass left behind: they are the lab's
    // loading state, reached from the same shell by the same reader.
    const { container } = render(
      <>
        <SkeletonQuestion />
        <SkeletonGrid />
      </>,
    )
    const moving = animated(container)
    expect(moving.length).toBe(2)
    for (const el of moving) {
      expect(el.className).toContain('motion-reduce:animate-none')
    }
  })

  it('stops the live-stat pulse under reduced motion', async () => {
    const { container } = render(<HomeStats />)
    // The Backend stat pulses only once the probe succeeds.
    await waitFor(() => expect(screen.getByText('Online')).toBeInTheDocument())
    const moving = animated(container)
    expect(moving.length).toBeGreaterThan(0)
    for (const el of moving) {
      expect(el.className).toContain('motion-reduce:animate-none')
    }
  })
})
