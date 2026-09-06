import ReviewQueue from '@/components/ReviewQueue'
import { server } from '@/mocks/server'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

/**
 * BL-20260811-01. Spec 029 gave the HITL loop admin + CLI surfaces only, so a
 * reviewer without a shell could not work the queue. These tests hold the web
 * half to the two things that actually matter for an audit trail: a decision
 * carries a rationale, and a failed graph write is *shown* rather than
 * reported as a success.
 */

const BASE = 'http://localhost:8000'

describe('ReviewQueue', () => {
  it('lists pending quarantined documents with reason and confidence', async () => {
    render(<ReviewQueue />)

    const list = await screen.findByRole('region', {
      name: /Quarantined documents/i,
    })
    expect(await within(list).findByText('cl-9001')).toBeInTheDocument()
    expect(within(list).getByText('courtlistener')).toBeInTheDocument()
    expect(within(list).getByText('confidence 0.42')).toBeInTheDocument()
    expect(within(list).getByText('low_confidence')).toBeInTheDocument()
  })

  it('shows per-status counts so the tabs cost one request', async () => {
    render(<ReviewQueue />)
    expect(
      await screen.findByRole('button', { name: /Needs attention \(1\)/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pending \(1\)/i })).toBeInTheDocument()
  })

  it('opens a document and renders its payload and metadata', async () => {
    render(<ReviewQueue />)

    fireEvent.click(await screen.findByText('cl-9001'))

    const detail = screen.getByRole('region', { name: /Review detail/i })
    expect(await within(detail).findByText('cl-9001')).toBeInTheDocument()
    expect(within(detail).getByText('pending')).toBeInTheDocument()
    expect(within(detail).getByText(/Doe v\. Roe/)).toBeInTheDocument()
  })

  it('refuses to reject without a rationale', async () => {
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    await screen.findByLabelText(/Rationale/i)

    fireEvent.click(screen.getByRole('button', { name: /^Reject$/i }))

    expect(
      await screen.findByText(/A rejection needs a rationale/i),
    ).toBeInTheDocument()
  })

  it('records a rejection with its rationale', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post(`${BASE}/api/ingestion/reviews/reject`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({
          review: {
            id: 'cl-9001',
            source: 'courtlistener',
            kind: 'case',
            confidence: 0.42,
            reason: 'low_confidence',
            created_at: null,
            reviewed_at: '2026-09-05T00:00:00Z',
            approved: false,
            reviewer: 'alice',
            review_note: 'wrong jurisdiction',
            committed_at: null,
            commit_error: '',
          },
          committed: false,
        })
      }),
    )
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    await screen.findByLabelText(/Rationale/i)

    fireEvent.change(screen.getByLabelText(/Reviewer/i), {
      target: { value: 'alice' },
    })
    fireEvent.change(screen.getByLabelText(/Rationale/i), {
      target: { value: 'wrong jurisdiction' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Reject$/i }))

    expect(await screen.findByText(/Nothing was written to the graph/i)).toBeInTheDocument()
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({
      id: 'cl-9001',
      reviewer: 'alice',
      note: 'wrong jurisdiction',
    })
  })

  it('reports a successful approve-and-commit', async () => {
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    await screen.findByLabelText(/Rationale/i)

    fireEvent.click(screen.getByRole('button', { name: /Approve & commit/i }))

    expect(
      await screen.findByText(/Approved and committed \(2 edge\(s\)\)/i),
    ).toBeInTheDocument()
  })

  it('surfaces a failed commit instead of reporting success', async () => {
    server.use(
      http.post(`${BASE}/api/ingestion/reviews/approve`, () =>
        HttpResponse.json({
          review: {
            id: 'cl-9001',
            source: 'courtlistener',
            kind: 'case',
            confidence: 0.42,
            reason: 'low_confidence',
            created_at: null,
            reviewed_at: '2026-09-05T00:00:00Z',
            approved: true,
            reviewer: '',
            review_note: '',
            committed_at: null,
            commit_error: 'Neo4jError: connection refused',
          },
          committed: false,
          edges: 0,
          commit_error: 'Neo4jError: connection refused',
        }),
      ),
    )
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    await screen.findByLabelText(/Rationale/i)

    fireEvent.click(screen.getByRole('button', { name: /Approve & commit/i }))

    // Said twice on purpose: once as the outcome of this action (role=status)
    // and once as the row's standing state (role=alert), because the row is
    // approved yet absent from the corpus until someone fixes it.
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/Neo4jError: connection refused/)
    expect(screen.getByRole('alert')).toHaveTextContent(
      /the graph write failed, so this item is not in the corpus/i,
    )
  })

  it('renders the commit_error state on a row that already failed', async () => {
    render(<ReviewQueue />)
    fireEvent.click(
      await screen.findByRole('button', { name: /Needs attention/i }),
    )

    const list = screen.getByRole('region', { name: /Quarantined documents/i })
    expect(
      await within(list).findByText('us-co/crs/18-3-102'),
    ).toBeInTheDocument()
    expect(
      within(list).getByText(/Commit failed — not in the graph/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByText('us-co/crs/18-3-102'))
    expect(
      await screen.findByText(/unsupported quarantine kind/i),
    ).toBeInTheDocument()
  })

  it('reports an empty queue as a state, not as idleness', async () => {
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByRole('button', { name: /Rejected/i }))

    expect(
      await screen.findByText(/An empty queue means no document is in this state/i),
    ).toBeInTheDocument()
  })

  it('re-extracts a row and reports the fresh score without committing', async () => {
    // BL-20260906-04: the third verb, on the web surface too.
    let approved = 0
    server.use(
      http.post(`${BASE}/api/ingestion/reviews/approve`, () => {
        approved += 1
        return HttpResponse.json({ review: {}, committed: true })
      }),
    )
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    fireEvent.click(
      await screen.findByRole('button', { name: /^Re-extract$/i }),
    )

    expect(
      await screen.findByText(/now clears the threshold/i),
    ).toBeInTheDocument()
    expect(approved).toBe(0)
  })

  it('says so when today\'s extractor would still quarantine the row', async () => {
    server.use(
      http.post(`${BASE}/api/ingestion/reviews/re-extract`, () =>
        HttpResponse.json({
          review: {},
          reextracted: true,
          previous_confidence: 0.42,
          confidence: 0.44,
          clears_threshold: false,
          n_citations: 0,
        }),
      ),
    )
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    fireEvent.click(
      await screen.findByRole('button', { name: /^Re-extract$/i }),
    )

    expect(
      await screen.findByText(/would still quarantine it/i),
    ).toBeInTheDocument()
  })

  it('surfaces a kind with no re-extraction path', async () => {
    server.use(
      http.post(`${BASE}/api/ingestion/reviews/re-extract`, () =>
        HttpResponse.json({ detail: 'no re-extraction path' }, { status: 422 }),
      ),
    )
    render(<ReviewQueue />)
    fireEvent.click(await screen.findByText('cl-9001'))
    fireEvent.click(
      await screen.findByRole('button', { name: /^Re-extract$/i }),
    )

    expect(
      await screen.findByText(/Review re-extract failed \(422\)/i),
    ).toBeInTheDocument()
  })

  it('surfaces a queue load failure', async () => {
    server.use(
      http.get(`${BASE}/api/ingestion/reviews`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<ReviewQueue />)
    expect(
      await screen.findByText(/Failed to load the queue/i),
    ).toBeInTheDocument()
  })
})
