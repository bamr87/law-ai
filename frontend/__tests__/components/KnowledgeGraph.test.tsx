import KnowledgeGraph from '@/components/KnowledgeGraph'
import { server } from '@/mocks/server'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithClient } from '../test-utils'

// Cytoscape touches the DOM with layouts that jsdom doesn't implement;
// stub the dynamic import so we can assert structural rendering only.
vi.mock('cytoscape', () => ({
  default: () => ({ destroy: vi.fn() }),
}))

const BASE = 'http://localhost:8000'

beforeEach(() => {
  server.use(
    http.get(`${BASE}/api/graph/stats`, () =>
      HttpResponse.json({
        available: true,
        cases: 7,
        citations: 12,
        cites_edges: 4,
      }),
    ),
    http.get(`${BASE}/api/graph/cases`, () =>
      HttpResponse.json({
        available: true,
        count: 2,
        cases: [
          {
            id: 'case-a',
            title: 'Roe v. Wade',
            court: 'Supreme Court',
            decided_at: '1973-01-22',
          },
          {
            id: 'case-b',
            title: 'Brown v. Board',
            court: 'Supreme Court',
            decided_at: '1954-05-17',
          },
        ],
      }),
    ),
    http.get(`${BASE}/api/graph/neighborhood/:id`, ({ params }) =>
      HttpResponse.json({
        available: true,
        nodes: [
          {
            data: {
              id: params.id as string,
              label: 'Selected',
              type: 'Case',
              court: 'Supreme Court',
            },
          },
          {
            data: { id: 'cit:410 us 113', label: '410 U.S. 113', type: 'Citation' },
          },
        ],
        edges: [
          {
            data: {
              id: `hc:${params.id as string}->cit:410 us 113`,
              source: params.id as string,
              target: 'cit:410 us 113',
              type: 'HAS_CITATION',
            },
          },
        ],
      }),
    ),
  )
})

describe('KnowledgeGraph', () => {
  it('renders Cases + Neighborhood headings and stats (AC-6)', async () => {
    renderWithClient(<KnowledgeGraph />)
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Cases' }),
      ).toBeInTheDocument()
      expect(
        screen.getByRole('heading', { name: 'Neighborhood' }),
      ).toBeInTheDocument()
    })
    // Stats strip values
    await waitFor(() => {
      expect(screen.getByText('7')).toBeInTheDocument()
      expect(screen.getByText('12')).toBeInTheDocument()
    })
    // Cytoscape canvas mounts
    expect(screen.getByTestId('graph-canvas')).toBeInTheDocument()
  })

  it('lists cases from the API and auto-selects the first', async () => {
    renderWithClient(<KnowledgeGraph />)
    await waitFor(() => {
      expect(screen.getAllByText('Roe v. Wade').length).toBeGreaterThan(0)
      expect(screen.getByText('Brown v. Board')).toBeInTheDocument()
    })
    // Auto-selected case loads its neighborhood (2 nodes from the mock).
    await waitFor(() => {
      expect(screen.getByText('2 nodes')).toBeInTheDocument()
    })
  })

  it('shows a banner when Neo4j is unavailable', async () => {
    server.use(
      http.get(`${BASE}/api/graph/stats`, () =>
        HttpResponse.json({
          available: false,
          cases: 0,
          citations: 0,
          cites_edges: 0,
        }),
      ),
      http.get(`${BASE}/api/graph/cases`, () =>
        HttpResponse.json({ available: false, count: 0, cases: [] }),
      ),
    )
    renderWithClient(<KnowledgeGraph />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Neo4j is not reachable/)
    })
  })
})
