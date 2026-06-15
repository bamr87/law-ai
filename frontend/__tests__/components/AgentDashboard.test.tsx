import AgentDashboard from '@/components/AgentDashboard'
import { server } from '@/mocks/server'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const BASE = 'http://localhost:8000'

beforeEach(() => {
  server.use(
    http.get(`${BASE}/api/agents`, () =>
      HttpResponse.json({
        count: 2,
        agents: [
          { name: 'LegalAnalyst', module: 'app.agents.crews.legal_analyst' },
          { name: 'PrecedentHunter', module: 'app.agents.crews.precedent_hunter' },
        ],
      }),
    ),
    http.get(`${BASE}/api/agents/runs`, () =>
      HttpResponse.json({
        count: 1,
        runs: [
          {
            trace_id: 't-1',
            agent: 'LegalAnalyst',
            type: 'agent_call',
            timestamp: '2026-04-29T12:00:00Z',
            latency_ms: 42,
          },
        ],
      }),
    ),
    http.get(`${BASE}/api/agents/backlog`, () =>
      HttpResponse.json({
        counts: { open: 3, claimed: 1, done: 5, total: 9 },
        open: [
          { id: 'BL-20260101-01', kind: 'feature', severity: 'high', title: 'Do thing' },
        ],
        claimed: [],
        done: [],
      }),
    ),
    http.get(`${BASE}/api/agents/specs`, () =>
      HttpResponse.json({
        count: 1,
        specs: [{ id: '003-agent-ops-dashboard', status: 'planned' }],
      }),
    ),
    http.get(`${BASE}/api/agents/autonomy`, () =>
      HttpResponse.json({
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
        ],
        recent_violations: [],
      }),
    ),
    http.get(`${BASE}/api/agents/sessions`, () =>
      HttpResponse.json({
        count: 1,
        sessions: [
          {
            session_id: 'sess-xyz',
            agent_source: 'claude_code',
            agent_name: 'Evolution Pilot',
            kind: 'evolve',
            status: 'completed',
            started_at: '2026-06-15T11:55:00Z',
            ended_at: '2026-06-15T12:00:00Z',
            root_trace_id: 't-1',
            spec_claimed: 'specs/099-demo',
            backlog_items_added: ['BL-20260615-09'],
            prs_created: ['pr#1'],
            summary: 'shipped a thing',
            metadata: {},
          },
        ],
      }),
    ),
  )
})

describe('AgentDashboard', () => {
  it('renders all four panel headings', async () => {
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText('Registry')).toBeInTheDocument()
      expect(screen.getByText('Recent Runs')).toBeInTheDocument()
      expect(screen.getByText('Backlog')).toBeInTheDocument()
      expect(screen.getByText('Specs')).toBeInTheDocument()
    })
  })

  it('renders one card per registered agent (AC-6)', async () => {
    render(<AgentDashboard />)
    const cards = await screen.findAllByTestId('registry-card')
    expect(cards).toHaveLength(2)
    expect(cards[0]).toHaveTextContent('LegalAnalyst')
    expect(cards[1]).toHaveTextContent('PrecedentHunter')
  })

  it('shows backlog counts and recent run rows', async () => {
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText(/Open: 3/)).toBeInTheDocument()
      expect(screen.getByText(/Claimed: 1/)).toBeInTheDocument()
      expect(screen.getByText(/Done: 5/)).toBeInTheDocument()
    })
    expect(screen.getByText('003-agent-ops-dashboard')).toBeInTheDocument()
  })

  it('renders the autonomy panel and session ledger (WS3/WS4)', async () => {
    render(<AgentDashboard />)
    await waitFor(() => {
      // Autonomy mission-control: kill-switch state + a session-ledger row.
      expect(screen.getByText('kill-switch OFF')).toBeInTheDocument()
      expect(screen.getByText('Sessions')).toBeInTheDocument()
    })
    expect(screen.getByText(/specs\/099-demo/)).toBeInTheDocument()
    expect(screen.getByText('+1 BL')).toBeInTheDocument()
  })

  it('surfaces panel-level errors without crashing the page', async () => {
    server.use(
      http.get(`${BASE}/api/agents/runs`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Failed to load/)
    })
    // Other panels still render
    expect(screen.getByText('Registry')).toBeInTheDocument()
  })
})

// --- Spec 008 AC-6: forward NEXT_PUBLIC_AGENT_API_KEY as X-API-Key ---

describe('AgentDashboard auth header (spec 008)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('does not send X-API-Key when env var is unset', async () => {
    const seen: (string | null)[] = []
    server.use(
      http.get(`${BASE}/api/agents`, ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json({ count: 0, agents: [] })
      }),
      http.get(`${BASE}/api/agents/runs`, ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json({ count: 0, runs: [] })
      }),
      http.get(`${BASE}/api/agents/backlog`, ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json({
          counts: { open: 0, claimed: 0, done: 0, total: 0 },
          open: [],
          claimed: [],
          done: [],
        })
      }),
      http.get(`${BASE}/api/agents/specs`, ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json({ count: 0, specs: [] })
      }),
    )
    render(<AgentDashboard />)
    await waitFor(() => expect(seen.length).toBe(4))
    for (const value of seen) expect(value).toBeNull()
  })

  it('forwards X-API-Key when NEXT_PUBLIC_AGENT_API_KEY is set', async () => {
    vi.stubEnv('NEXT_PUBLIC_AGENT_API_KEY', 's3cret')
    const seen: (string | null)[] = []
    const handler =
      (
        body: Record<string, unknown>,
      ): Parameters<typeof http.get>[1] =>
      ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json(body)
      }
    server.use(
      http.get(`${BASE}/api/agents`, handler({ count: 0, agents: [] })),
      http.get(
        `${BASE}/api/agents/runs`,
        handler({ count: 0, runs: [] }),
      ),
      http.get(
        `${BASE}/api/agents/backlog`,
        handler({
          counts: { open: 0, claimed: 0, done: 0, total: 0 },
          open: [],
          claimed: [],
          done: [],
        }),
      ),
      http.get(`${BASE}/api/agents/specs`, handler({ count: 0, specs: [] })),
    )
    render(<AgentDashboard />)
    await waitFor(() => expect(seen.length).toBe(4))
    for (const value of seen) expect(value).toBe('s3cret')
  })
})
