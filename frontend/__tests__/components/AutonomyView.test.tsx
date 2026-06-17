import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import AutonomyView from '@/components/AutonomyView'
import { server } from '@/mocks/server'
import { renderWithClient as render } from '../test-utils'

const BASE = 'http://localhost:8000'

const autonomy = (overrides: Record<string, unknown> = {}) => ({
  enabled: false,
  allowed_sources: ['courtlistener'],
  last_cycle: {
    cycle_id: 'c-1',
    cycle_type: 'evolve',
    status: 'ok',
    duration_ms: 1234,
    completed_at: '2026-06-15T12:00:00Z',
  },
  recent_cycles: [
    {
      cycle_id: 'c-1',
      cycle_type: 'evolve',
      status: 'ok',
      duration_ms: 1234,
      completed_at: '2026-06-15T12:00:00Z',
    },
    {
      cycle_id: 'c-2',
      cycle_type: 'ingest',
      status: 'error',
      duration_ms: 5678,
      completed_at: '2026-06-15T11:00:00Z',
    },
  ],
  recent_violations: [],
  ...overrides,
})

beforeEach(() => {
  server.use(
    http.get(`${BASE}/api/agents/autonomy`, () => HttpResponse.json(autonomy())),
  )
})

describe('AutonomyView', () => {
  it('shows the kill-switch banner, sources, and recent cycles', async () => {
    render(<AutonomyView />)
    await waitFor(() =>
      expect(screen.getByText(/Kill-switch engaged/i)).toBeInTheDocument(),
    )
    // Allowed source (appears as a badge + in the stat hint) + both cycle rows.
    expect(screen.getAllByText('courtlistener').length).toBeGreaterThan(0)
    expect(screen.getByText('evolve')).toBeInTheDocument()
    expect(screen.getByText('ingest')).toBeInTheDocument()
    expect(screen.getByText('No policy violations recorded. 🎉')).toBeInTheDocument()
  })

  it('shows the enabled banner when autonomy is on', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy`, () =>
        HttpResponse.json(autonomy({ enabled: true })),
      ),
    )
    render(<AutonomyView />)
    await waitFor(() =>
      expect(screen.getByText('Autonomy enabled')).toBeInTheDocument(),
    )
  })

  it('surfaces policy violations when present', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy`, () =>
        HttpResponse.json(
          autonomy({
            recent_violations: [
              { timestamp: '2026-06-15T12:00:00Z', payload: { rule: 'I1', detail: 'auto-merge blocked' } },
            ],
          }),
        ),
      ),
    )
    render(<AutonomyView />)
    await waitFor(() =>
      expect(screen.getByText(/auto-merge blocked/)).toBeInTheDocument(),
    )
    expect(screen.getByText('violation')).toBeInTheDocument()
  })
})
