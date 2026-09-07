/** The public face of a share link (BL-20260429-26). */
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import SharedAnalysisPanel from '@/components/SharedAnalysis'
import { createShareLink, revokeShareLink } from '@/lib/api'
import { server } from '@/mocks/server'

const shared = {
  id: 'an-share01',
  timestamp: '2026-09-05T12:00:00Z',
  latency_ms: 900,
  confidence: 0.9,
  requires_human_review: false,
  irac: {
    issue: 'Was the floor a hazard?',
    rule: 'Reasonable care to invitees.',
    application: 'Unmarked for 30 minutes.',
    conclusion: 'Plaintiff likely prevails.',
    sources: [],
    confidence: 0.9,
  },
  precedents: {
    precedents: [
      {
        case_id: 'c-1',
        title: 'Smith v. Acme',
        court: 'CA Sup. Ct.',
        year: 1999,
        relevance_score: 0.9,
        distinguishing_factors: [],
        url: 'https://example.test/smith',
      },
    ],
    summary: 'One on-point case.',
    confidence: 0.9,
  },
  agent_trace: [],
  persisted: true,
  created_at: '2026-09-05T12:00:00Z',
  trace_id: 'trace-parent',
  child_trace_ids: [],
  request: { text: 'Plaintiff slipped on a wet floor.' },
  shared: true,
  slug: 'wet-floor-memo',
  label: 'For the partner',
  disclaimer: 'Not legal advice.',
}

describe('SharedAnalysisPanel', () => {
  it('renders the analysis and the mandatory disclaimer', async () => {
    server.use(
      http.get('http://localhost:8000/api/shared/wet-floor-memo', () =>
        HttpResponse.json(shared),
      ),
    )
    render(<SharedAnalysisPanel slug="wet-floor-memo" />)

    await waitFor(() =>
      expect(screen.getByText(/Plaintiff likely prevails/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/Not legal advice/i)).toBeInTheDocument()
    expect(screen.getByText('Smith v. Acme')).toBeInTheDocument()
    expect(screen.getByText(/Plaintiff slipped on a wet floor/)).toBeInTheDocument()
    expect(screen.getByText('For the partner')).toBeInTheDocument()
  })

  it('says the link is unavailable for a revoked or unknown slug', async () => {
    server.use(
      http.get('http://localhost:8000/api/shared/gone', () =>
        HttpResponse.json({ detail: 'share link not found' }, { status: 404 }),
      ),
    )
    render(<SharedAnalysisPanel slug="gone" />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not available/i)
    // The disclaimer stays even when there is nothing to show.
    expect(screen.getByText(/Not legal advice/i)).toBeInTheDocument()
  })
})

describe('share link client', () => {
  it('mints a slug and returns its shareable URL', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post(
        'http://localhost:8000/api/analysis/an-share01/share',
        async ({ request }) => {
          bodies.push(await request.json())
          return HttpResponse.json(
            {
              slug: 'wet-floor-memo',
              url: '/shared/wet-floor-memo',
              analysis_id: 'an-share01',
              label: '',
              created_at: null,
              revoked: false,
            },
            { status: 201 },
          )
        },
      ),
    )
    const link = await createShareLink('an-share01', { slug: 'wet-floor-memo' })
    expect(link.url).toBe('/shared/wet-floor-memo')
    expect(bodies[0]).toMatchObject({ slug: 'wet-floor-memo' })
  })

  it('surfaces the backend refusal when the caller is not signed in', async () => {
    server.use(
      http.post('http://localhost:8000/api/analysis/an-share01/share', () =>
        HttpResponse.json({ detail: 'sign in to share an analysis' }, { status: 403 }),
      ),
    )
    await expect(createShareLink('an-share01')).rejects.toThrow(/sign in to share/)
  })

  it('revokes a link', async () => {
    server.use(
      http.delete(
        'http://localhost:8000/api/analysis/an-share01/share/wet-floor-memo',
        () =>
          HttpResponse.json({
            slug: 'wet-floor-memo',
            url: '/shared/wet-floor-memo',
            analysis_id: 'an-share01',
            label: '',
            created_at: null,
            revoked: true,
          }),
      ),
    )
    const link = await revokeShareLink('an-share01', 'wet-floor-memo')
    expect(link.revoked).toBe(true)
  })
})
