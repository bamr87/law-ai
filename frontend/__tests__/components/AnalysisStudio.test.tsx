import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, it, expect } from 'vitest'

import AnalysisStudio from '@/components/AnalysisStudio'
import { server } from '@/mocks/server'

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
    expect(screen.getByText(/LegalAnalyst/)).toBeInTheDocument()
    expect(screen.getByText(/PrecedentHunter/)).toBeInTheDocument()
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

    // Wording tightened from "recommended" to "required": the backend flag
    // is now a hard gate (degraded agents force it), not a suggestion.
    const alert = await screen.findByText(/Human review required/i)
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

// --- BL-20260810-07 / spec 030: UPL guardrail + honest review reasons ---

describe('AnalysisStudio safety surfaces', () => {
  it('shows the not-legal-advice disclaimer before any analysis is run', () => {
    render(<AnalysisStudio />)
    expect(screen.getByText(/Not legal advice/i)).toBeInTheDocument()
    expect(
      screen.getByText(/consult a licensed attorney in your jurisdiction/i),
    ).toBeInTheDocument()
  })

  it('keeps the disclaimer visible alongside generated analysis', async () => {
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
    expect(screen.getByText(/Not legal advice/i)).toBeInTheDocument()
  })

  it('states the degraded reason for review, not the confidence threshold', async () => {
    const body = fullResponse({ requires_human_review: true, confidence: 0.0 })
    ;(body.irac as Record<string, unknown>).degraded = true
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(body),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument(),
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/No analysis engine ran/i)
    expect(alert).not.toHaveTextContent(/below the 70% threshold/i)
  })

  it('falls back to the confidence threshold reason when no flag is set', async () => {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(
          fullResponse({ requires_human_review: true, confidence: 0.5 }),
        ),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/below the 70% threshold/i)
  })

  it('renders the corpus coverage envelope when the backend supplies it', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).retrieval = {
      queries: ['premises liability wet floor'],
      result_count: 0,
      coverage_note:
        'No passages were retrieved from the knowledge graph. Absence of ' +
        'results in this corpus does NOT mean no such law exists.',
    }
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(body),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Corpus coverage/i })).toBeInTheDocument(),
    )
    // Scope to the coverage section: the standing disclaimer carries similar
    // "absence of results" wording, so a page-wide query matches twice.
    const coverage = screen.getByRole('region', { name: /Corpus coverage/i })
    expect(coverage).toHaveTextContent(/does NOT mean no such law exists/i)
    expect(coverage).toHaveTextContent(/premises liability wet floor/i)
  })
})

// --- Spec 033: verified-citation badges + live trace fallback ---

describe('AnalysisStudio citation verification', () => {
  it('labels unverified citations instead of hiding them', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).sources = [
      { title: 'Real v. Cite', url: 'https://example.test/real', verified: true },
      { title: 'Phantom v. Mirage', url: '', verified: false },
    ]
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(body),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /IRAC Brief/i })).toBeInTheDocument(),
    )
    // Both citations are shown; the unresolved one is flagged, not dropped.
    expect(screen.getByText('Phantom v. Mirage')).toBeInTheDocument()
    expect(screen.getByText(/unverified/i)).toBeInTheDocument()
    expect(screen.getByText(/verified in graph/i)).toBeInTheDocument()
  })

  it('omits badges when the backend does not report verification', async () => {
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
    expect(screen.queryByText(/unverified/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/verified in graph/i)).not.toBeInTheDocument()
  })

  it('still completes the analysis when the live stream cannot connect', async () => {
    // Streaming is an enhancement: a failed socket must not block the run.
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
    // No live panel rendered because no step events ever arrived.
    expect(
      screen.queryByRole('heading', { name: /Agents reporting/i }),
    ).not.toBeInTheDocument()
  })
})
