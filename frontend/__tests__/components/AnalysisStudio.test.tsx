import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, it, expect } from 'vitest'

import AnalysisStudio from '@/components/AnalysisStudio'
import { server } from '@/mocks/server'
import { renderWithClient as render } from '../test-utils'

const fullResponse = (overrides: Record<string, unknown> = {}) => ({
  id: 'an-abc123',
  timestamp: '2026-04-29T18:30:00+00:00',
  latency_ms: 42,
  confidence: 0.85,
  requires_human_review: false,
  irac: {
    issue: 'Negligence on premises liability theory',
    rule: 'Reasonable care to invitees',
    application: 'Wet floor unmarked for 30 minutes',
    conclusion: 'Plaintiff likely to prevail',
    sources: [{ title: 'Roe v. Wade', url: 'https://example.test/roe' }],
    confidence: 0.82,
    reasoning_trace: ['issue spotting', 'rule synthesis'],
    trace_id: 'trace-1234',
  },
  precedents: {
    precedents: [
      {
        case_id: 'c-1',
        title: 'Smith v. Acme',
        court: 'CA Sup. Ct.',
        year: 1999,
        relevance_score: 0.91,
        distinguishing_factors: ['signage present in Smith'],
        url: 'https://example.test/smith',
      },
    ],
    summary: 'One on-point negligence case from California.',
    confidence: 0.88,
    trace_id: 'trace-5678',
  },
  agent_trace: [
    {
      agent: 'LegalAnalyst',
      trace_id: 'trace-1234',
      latency_ms: 25,
      confidence: 0.82,
    },
    {
      agent: 'PrecedentHunter',
      trace_id: 'trace-5678',
      latency_ms: 30,
      confidence: 0.88,
    },
  ],
  ...overrides,
})

describe('AnalysisStudio', () => {
  it('renders the input form with sample loader', () => {
    render(<AnalysisStudio />)
    expect(screen.getByLabelText(/Fact pattern/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run analysis/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Load sample/i })).toBeInTheDocument()
  })

  it('loads the sample text and enables the submit button', () => {
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    const textarea = screen.getByLabelText(/Fact pattern/i) as HTMLTextAreaElement
    expect(textarea.value).toMatch(/wet floor/i)
    expect(screen.getByRole('button', { name: /Run analysis/i })).not.toBeDisabled()
  })

  it('submits and renders IRAC + precedents + agent trace', async () => {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(fullResponse()),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /IRAC Brief/i })).toBeInTheDocument(),
    )
    expect(
      screen.getByText(/Negligence on premises liability theory/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Smith v. Acme')).toBeInTheDocument()
    expect(screen.getByText(/Agent Execution Trace/i)).toBeInTheDocument()
    // Crew names appear in both the tagline and the agent trace.
    expect(screen.getAllByText(/LegalAnalyst/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/PrecedentHunter/).length).toBeGreaterThan(0)
    expect(screen.getByText(/an-abc123/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the HITL banner when requires_human_review is true', async () => {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(
          fullResponse({ requires_human_review: true, confidence: 0.42 }),
        ),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    const alert = await screen.findByText(/Human review recommended/i)
    expect(alert).toBeInTheDocument()
    expect(screen.getAllByText(/42%/).length).toBeGreaterThan(0)
  })

  it('renders an error banner when the API fails', async () => {
    server.use(
      http.post('http://localhost:8000/api/analysis', () =>
        HttpResponse.text('boom', { status: 500 }),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Analysis failed \(500\)/)
  })
})
