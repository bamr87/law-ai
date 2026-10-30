import AutonomyDashboard from '@/components/AutonomyDashboard'
import { server } from '@/mocks/server'
import { render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

/**
 * BL-20260511-03. The dashboard's whole job is to answer three questions
 * about the nightly loops, so the tests check the answers — and, just as
 * hard, the *absence* of an answer: `history.jsonl` and Postgres are things a
 * fresh checkout does not have, and a panel that renders an empty chart there
 * is claiming a score of zero it never measured. (The lowest-coverage panel
 * left with the test pillar, ADR 0008.)
 */

const BASE = 'http://localhost:8000'

describe('AutonomyDashboard', () => {
  it('renders the three read-only panels', async () => {
    render(<AutonomyDashboard />)

    expect(
      await screen.findByRole('region', {
        name: /LegalBench accuracy over time/i,
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: /Recently quarantined documents/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: /Recent autonomy cycles/i }),
    ).toBeInTheDocument()
  })

  it('lists recent cycles by kind, status and duration', async () => {
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recent autonomy cycles/i,
    })
    // The region renders before its rows arrive, so the first read inside
    // it is awaited; everything below lands in the same commit.
    expect(await within(panel).findByText('digest')).toBeInTheDocument()
    expect(within(panel).getByText('ok')).toBeInTheDocument()
    expect(within(panel).getByText('12.0s')).toBeInTheDocument()
    // The failing cycle is the one an operator came for, and it says so.
    expect(within(panel).getByText(/corpus_growth/)).toBeInTheDocument()
    expect(within(panel).getByText('(courtlistener)')).toBeInTheDocument()
    expect(within(panel).getByText('error')).toBeInTheDocument()
    expect(within(panel).getByText('450ms')).toBeInTheDocument()
  })

  it('distinguishes an unreadable run table from a loop that never ran', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/runs`, () =>
        HttpResponse.json({
          available: false,
          runs: [],
          count: 0,
          kind: '',
          by_status: {},
        }),
      ),
    )
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recent autonomy cycles/i,
    })
    expect(
      await within(panel).findByText(/is Postgres up/i),
    ).toBeInTheDocument()
    expect(
      within(panel).queryByText(/No cycle has run yet/i),
    ).not.toBeInTheDocument()
  })

  it('says no cycle has run when the table is simply empty', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/runs`, () =>
        HttpResponse.json({
          available: true,
          runs: [],
          count: 0,
          kind: '',
          by_status: {},
        }),
      ),
    )
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recent autonomy cycles/i,
    })
    // The region renders as soon as the panel mounts, before its rows
    // resolve, so the text inside it has to be awaited too — a sync query
    // here races the load and fails on a slower runner.
    expect(
      await within(panel).findByText(/No cycle has run yet/i),
    ).toBeInTheDocument()
  })

  it('draws one labelled sparkline per LegalBench subset', async () => {
    render(<AutonomyDashboard />)

    const spark = await screen.findByRole('img', {
      name: /abercrombie: 3 runs, latest 62\.0%/i,
    })
    expect(spark.tagName.toLowerCase()).toBe('svg')
    // The trend is stated in words too — a sparkline alone is not accessible.
    expect(screen.getByText('+12.0pp')).toBeInTheDocument()
    expect(screen.getByText('62.0%')).toBeInTheDocument()
  })

  it('lists quarantined documents with confidence and kind', async () => {
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recently quarantined documents/i,
    })
    expect(await within(panel).findByText('cl-9001')).toBeInTheDocument()
    expect(within(panel).getByText('case')).toBeInTheDocument()
    expect(within(panel).getByText('conf 0.42')).toBeInTheDocument()
    expect(
      within(panel).getByText(/citation resolver below threshold/i),
    ).toBeInTheDocument()
  })

  it('says "not measured yet" instead of drawing an empty chart', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/legalbench-history`, () =>
        HttpResponse.json({
          available: false,
          runs: [],
          series: [],
          count: 0,
        }),
      ),
    )
    render(<AutonomyDashboard />)

    const history = await screen.findByRole('region', {
      name: /LegalBench accuracy over time/i,
    })
    expect(
      await within(history).findByText(/Not measured yet/i),
    ).toBeInTheDocument()
    expect(within(history).getByText(/history\.jsonl/i)).toBeInTheDocument()
    expect(within(history).queryByRole('img')).not.toBeInTheDocument()
  })

  it('distinguishes an unreachable queue from an empty one', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/recent-quarantine`, () =>
        HttpResponse.json({ available: false, documents: [], count: 0 }),
      ),
    )
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recently quarantined documents/i,
    })
    expect(
      await within(panel).findByText(/is Postgres up/i),
    ).toBeInTheDocument()
  })

  it('reports an empty queue as reviewed, not as unavailable', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/recent-quarantine`, () =>
        HttpResponse.json({ available: true, documents: [], count: 0 }),
      ),
    )
    render(<AutonomyDashboard />)

    const panel = await screen.findByRole('region', {
      name: /Recently quarantined documents/i,
    })
    expect(
      await within(panel).findByText(/every extraction has been reviewed/i),
    ).toBeInTheDocument()
  })

  it('surfaces a failed request as an alert rather than blank space', async () => {
    server.use(
      http.get(`${BASE}/api/agents/autonomy/legalbench-history`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<AutonomyDashboard />)

    await waitFor(() => {
      const panel = screen.getByRole('region', {
        name: /LegalBench accuracy over time/i,
      })
      expect(within(panel).getByRole('alert')).toHaveTextContent(
        /Failed to load/i,
      )
    })
  })

  it('never renders a control that would start or approve anything', async () => {
    render(<AutonomyDashboard />)
    await screen.findByRole('region', { name: /Recent autonomy cycles/i })

    const labels = screen
      .getAllByRole('button')
      .map((b) => (b.textContent ?? '').toLowerCase())
    expect(labels).toEqual(['refresh'])
  })
})
