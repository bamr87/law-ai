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
        attribution: {
          court: 'CA Sup. Ct.',
          jurisdiction: 'us-ca',
          decided_at: '1999-06-01',
          authority: 'binding',
          opinion_part: 'majority',
        },
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
    expect(
      screen.getByRole('button', { name: /Load sample/i }),
    ).toBeInTheDocument()
  })

  it('loads the sample text and enables the submit button', () => {
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    const textarea = screen.getByLabelText(
      /Fact pattern/i,
    ) as HTMLTextAreaElement
    expect(textarea.value).toMatch(/wet floor/i)
    expect(
      screen.getByRole('button', { name: /Run analysis/i }),
    ).not.toBeDisabled()
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
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
    expect(
      screen.getByText(/Negligence on premises liability theory/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Smith v. Acme')).toBeInTheDocument()
    expect(screen.getByText(/Agent Execution Trace/i)).toBeInTheDocument()
    expect(screen.getByText(/LegalAnalyst/)).toBeInTheDocument()
    expect(screen.getByText(/PrecedentHunter/)).toBeInTheDocument()
    // The id now appears twice: in the trace and in the permalink
    // (BL-20260429-25).
    expect(screen.getAllByText(/an-abc123/).length).toBeGreaterThan(0)
    expect(
      screen.getByRole('link', { name: '/analysis?id=an-abc123' }),
    ).toBeInTheDocument()
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

  // BL-20260831-10: the cap used to eat the tail of a long paste silently.
  describe('input truncation', () => {
    const MAX_LEN = 20_000

    it('says how much of an over-long paste was dropped', () => {
      render(<AnalysisStudio />)
      const box = screen.getByLabelText(/Fact pattern/i)
      fireEvent.change(box, { target: { value: 'x'.repeat(MAX_LEN + 50) } })

      expect((box as HTMLTextAreaElement).value).toHaveLength(MAX_LEN)
      const warning = screen.getByTestId('truncation-warning')
      expect(warning).toHaveAttribute('role', 'status')
      expect(warning).toHaveTextContent(/Trimmed to 20,000 characters/)
      expect(warning).toHaveTextContent(/50 characters were not kept/)
    })

    it('shows nothing while the text fits, and clears once it does again', () => {
      render(<AnalysisStudio />)
      const box = screen.getByLabelText(/Fact pattern/i)
      fireEvent.change(box, { target: { value: 'short enough' } })
      expect(screen.queryByTestId('truncation-warning')).toBeNull()

      fireEvent.change(box, { target: { value: 'y'.repeat(MAX_LEN + 1) } })
      expect(screen.getByTestId('truncation-warning')).toHaveTextContent(
        /1 character was not kept/,
      )

      fireEvent.change(box, { target: { value: 'back under the cap' } })
      expect(screen.queryByTestId('truncation-warning')).toBeNull()
    })
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
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
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

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/No analysis engine ran/i)
    expect(alert).not.toHaveTextContent(/below the 70% threshold/i)
  })

  // BL-20260810-16: a degraded refusal must not be dressed up as a result.
  describe('engine state', () => {
    const runDegraded = async (irac: Record<string, unknown>) => {
      const body = fullResponse({
        requires_human_review: true,
        confidence: 0.0,
      })
      Object.assign(body.irac as Record<string, unknown>, {
        degraded: true,
        confidence: 0,
        ...irac,
      })
      server.use(
        http.post('http://localhost:8000/api/analysis', async () =>
          HttpResponse.json(body),
        ),
      )
      render(<AnalysisStudio />)
      fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
      fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
      return screen.findByTestId('engine-state')
    }

    it('tells an operator to start Ollama when the engine could not run', async () => {
      const panel = await runDegraded({
        degraded_reason: 'engine_unavailable',
        rule: '[ENGINE UNAVAILABLE] The LangGraph analysis engine could not run: probe failed',
      })
      expect(panel).toHaveTextContent(/Local LLM engine offline/i)
      expect(panel).toHaveTextContent('make local-ai-up')
      // No brief, no confidence pill, no precedent list to mistake for law.
      expect(screen.queryByRole('heading', { name: /IRAC Brief/i })).toBeNull()
      expect(screen.queryByText(/% confidence/)).toBeNull()
      expect(
        screen.queryByRole('heading', { name: /Relevant Precedents/i }),
      ).toBeNull()
      expect(screen.getByText(/No analysis produced/i)).toBeInTheDocument()
    })

    it('points at the provider chain when every tier failed', async () => {
      const panel = await runDegraded({
        degraded_reason: 'offline_fallback',
        rule: '[OFFLINE FALLBACK] No LLM provider was reachable — no analysis generated.',
      })
      expect(panel).toHaveTextContent(/No LLM provider reachable/i)
      expect(panel).toHaveTextContent('LLM_PROVIDER_CHAIN')
      expect(panel).not.toHaveTextContent('make local-ai-up')
    })

    it('reads the marker prefix when the payload predates degraded_reason', async () => {
      const panel = await runDegraded({
        rule: '[OFFLINE FALLBACK] No LLM provider was reachable — no analysis generated.',
      })
      expect(panel).toHaveTextContent(/No LLM provider reachable/i)
    })

    it('leaves a healthy result rendering as a brief', async () => {
      server.use(
        http.post('http://localhost:8000/api/analysis', async () =>
          HttpResponse.json(fullResponse()),
        ),
      )
      render(<AnalysisStudio />)
      fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
      fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: /IRAC Brief/i }),
        ).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('engine-state')).toBeNull()
    })
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
    expect(screen.getByRole('alert')).toHaveTextContent(
      /below the 70% threshold/i,
    )
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
      expect(
        screen.getByRole('heading', { name: /Corpus coverage/i }),
      ).toBeInTheDocument(),
    )
    // Scope to the coverage section: the standing disclaimer carries similar
    // "absence of results" wording, so a page-wide query matches twice.
    const coverage = screen.getByRole('region', { name: /Corpus coverage/i })
    expect(coverage).toHaveTextContent(/does NOT mean no such law exists/i)
    expect(coverage).toHaveTextContent(/premises liability wet floor/i)
  })

  it('renders jurisdictions and the decision-date span as labelled rows', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).retrieval = {
      queries: ['judicial review'],
      result_count: 2,
      jurisdictions_present: ['us-supreme'],
      jurisdiction_requested: 'us-ca',
      jurisdiction_absent: true,
      date_earliest: '1803-02-24',
      date_latest: '1821-03-03',
      coverage_note: '2 passage(s) retrieved.',
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
      expect(
        screen.getByRole('heading', { name: /Corpus coverage/i }),
      ).toBeInTheDocument(),
    )
    const coverage = screen.getByRole('region', { name: /Corpus coverage/i })
    expect(coverage).toHaveTextContent(/Jurisdictions present/i)
    expect(coverage).toHaveTextContent(/us-supreme/i)
    expect(coverage).toHaveTextContent(/Jurisdiction absent/i)
    expect(coverage).toHaveTextContent(/1803-02-24/)
    expect(coverage).toHaveTextContent(/1821-03-03/)
  })

  // BL-20260811-18: the flag has to survive a skim, so it gets a live-region
  // callout of its own rather than a clause inside the prose note.
  it('calls out an absent jurisdiction distinctly', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).retrieval = {
      queries: ['landlord duty to repair'],
      result_count: 3,
      jurisdictions_present: ['US-NY'],
      jurisdiction_requested: 'US-CA',
      jurisdiction_absent: true,
      coverage_note: '3 passage(s) retrieved.',
    }
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(body),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    const callout = await screen.findByTestId('jurisdiction-absent')
    expect(callout).toHaveAttribute('role', 'status')
    expect(callout).toHaveTextContent(
      /No results from the requested jurisdiction/i,
    )
    expect(callout).toHaveTextContent('US-CA')
    expect(callout).toHaveTextContent('US-NY')
    expect(callout).toHaveTextContent(/persuasive at best/i)
    // It lives inside the coverage panel, not floating elsewhere on the page.
    expect(
      screen.getByRole('region', { name: /Corpus coverage/i }),
    ).toContainElement(callout)
  })

  it('shows no jurisdiction callout when the corpus does cover the request', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).retrieval = {
      queries: ['landlord duty to repair'],
      result_count: 3,
      jurisdictions_present: ['US-CA'],
      jurisdiction_requested: 'US-CA',
      jurisdiction_absent: false,
      coverage_note: '3 passage(s) retrieved.',
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
      expect(
        screen.getByRole('heading', { name: /Corpus coverage/i }),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('jurisdiction-absent')).toBeNull()
  })
})

// --- Spec 033: verified-citation badges + live trace fallback ---

describe('AnalysisStudio citation verification', () => {
  it('labels unverified citations instead of hiding them', async () => {
    const body = fullResponse()
    ;(body.irac as Record<string, unknown>).sources = [
      {
        title: 'Real v. Cite',
        url: 'https://example.test/real',
        verified: true,
      },
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
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
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
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
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
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
    // No live panel rendered because no step events ever arrived.
    expect(
      screen.queryByRole('heading', { name: /Agents reporting/i }),
    ).not.toBeInTheDocument()
  })
})

// --- BL-20260810-13: durable LangGraph thread resume ---

describe('AnalysisStudio thread resume', () => {
  it('sends the typed thread_id and pre-fills it from the response', async () => {
    let seen: Record<string, unknown> | null = null
    const body = fullResponse()
    ;(body as Record<string, unknown>).langgraph_thread_id = 'lwf-server-1'
    server.use(
      http.post('http://localhost:8000/api/analysis', async ({ request }) => {
        seen = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(body)
      }),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.change(screen.getByLabelText(/Resume thread/i), {
      target: { value: 'lwf-abc123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() => expect(seen).not.toBeNull())
    expect(seen!.thread_id).toBe('lwf-abc123')
    // The response's thread id replaces it, so the next run continues it.
    await waitFor(() =>
      expect(screen.getByLabelText(/Resume thread/i)).toHaveValue(
        'lwf-server-1',
      ),
    )
  })

  it('omits thread_id entirely when the field is blank', async () => {
    let seen: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/analysis', async ({ request }) => {
        seen = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(fullResponse())
      }),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() => expect(seen).not.toBeNull())
    expect('thread_id' in seen!).toBe(false)
  })

  it('badges a run that resumed an existing thread', async () => {
    const body = fullResponse()
    ;(body as Record<string, unknown>).langgraph_thread_id = 'lwf-abc123'
    ;(body as Record<string, unknown>).resumed = true
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(body),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))

    await waitFor(() =>
      expect(screen.getByText(/^resumed$/i)).toBeInTheDocument(),
    )
  })
})

/**
 * The trace id is what a reviewer pastes into the audit store, so the chip's
 * eight-character elision must never be what leaves the page (BL-20260429-27).
 */
describe('AnalysisStudio trace id copy', () => {
  const LONG_TRACE = 'trace-0123456789abcdef'

  const renderWithTrace = async () => {
    const body = fullResponse()
    ;(body as Record<string, unknown>).agent_trace = [
      {
        agent: 'LegalAnalyst',
        trace_id: LONG_TRACE,
        latency_ms: 25,
        confidence: 0.82,
      },
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
      expect(screen.getByTestId('trace-id')).toBeInTheDocument(),
    )
  }

  const stubClipboard = (writeText: (text: string) => Promise<void>) => {
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    return () => {
      if (original) Object.defineProperty(navigator, 'clipboard', original)
      else delete (navigator as { clipboard?: unknown }).clipboard
    }
  }

  it('copies the whole id even though the chip elides it', async () => {
    const written: string[] = []
    const restore = stubClipboard(async (text) => {
      written.push(text)
    })
    try {
      await renderWithTrace()
      // The chip shows only the first eight characters.
      expect(screen.getByTestId('trace-id')).toHaveTextContent('trace-01…')
      expect(screen.getByTestId('trace-id')).not.toHaveTextContent(LONG_TRACE)

      const copy = screen.getByRole('button', {
        name: `Copy trace id ${LONG_TRACE}`,
      })
      fireEvent.click(copy)

      await waitFor(() => expect(copy).toHaveTextContent('Copied'))
      expect(written).toEqual([LONG_TRACE])
      // Screen-reader confirmation, not just a visual label swap.
      expect(screen.getByRole('status')).toHaveTextContent(
        /trace id copied to clipboard/i,
      )
    } finally {
      restore()
    }
  })

  it('does not claim success when the clipboard refuses', async () => {
    const restore = stubClipboard(async () => {
      throw new Error('clipboard blocked')
    })
    try {
      await renderWithTrace()
      const copy = screen.getByRole('button', {
        name: `Copy trace id ${LONG_TRACE}`,
      })
      fireEvent.click(copy)

      await waitFor(() => expect(copy).toHaveTextContent('Copy'))
      expect(copy).not.toHaveTextContent('Copied')
    } finally {
      restore()
    }
  })
})

// ---------------------------------------------------------------------------
// Constitution §13 attribution on the page itself (BL-20260803-04)
// ---------------------------------------------------------------------------

describe('AnalysisStudio source attribution', () => {
  async function renderResult(overrides: Record<string, unknown>) {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(fullResponse(overrides)),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
  }

  it('names the court, the date and the binding/persuasive weight', async () => {
    await renderResult({
      irac: {
        ...fullResponse().irac,
        sources: [
          {
            title: 'Meyer v. Uber',
            url: 'https://example.test/meyer',
            verified: true,
            attribution: {
              court: 'us-ca-2',
              jurisdiction: 'us-ca',
              decided_at: '2017-08-17',
              authority: 'binding',
              opinion_part: 'majority',
            },
          },
        ],
      },
    })
    expect(
      screen.getByText(/us-ca-2 · 2017-08-17 · binding/),
    ).toBeInTheDocument()
  })

  it('says so when a source names no issuing authority', async () => {
    await renderResult({
      irac: {
        ...fullResponse().irac,
        sources: [
          {
            title: 'Ghost v. Nobody',
            url: '',
            verified: true,
            attribution: {
              court: null,
              jurisdiction: null,
              decided_at: null,
              authority: 'unknown',
              opinion_part: 'unknown',
            },
          },
        ],
      },
    })
    expect(screen.getByText('no issuing authority')).toBeInTheDocument()
  })

  it('draws the binding weight on each precedent (BL-20260905-84)', async () => {
    await renderResult({})
    expect(screen.getByText('1999-06-01 · us-ca')).toBeInTheDocument()
    const weight = screen.getByTitle(
      /This authority is binding for the requested jurisdiction/i,
    )
    expect(weight).toHaveTextContent('binding')
  })

  it('labels a precedent the graph cannot attribute', async () => {
    await renderResult({
      precedents: {
        ...fullResponse().precedents,
        precedents: [
          {
            ...fullResponse().precedents.precedents[0],
            attribution: {
              court: null,
              jurisdiction: null,
              decided_at: null,
              authority: 'unknown',
              opinion_part: 'unknown',
            },
          },
        ],
      },
    })
    expect(screen.getByText('no issuing authority')).toBeInTheDocument()
  })

  it('explains an under-attributed precedent set in the review banner', async () => {
    await renderResult({
      requires_human_review: true,
      precedents: { ...fullResponse().precedents, requires_review: true },
    })
    expect(
      screen.getByText(/carries no issuing authority/i),
    ).toBeInTheDocument()
  })
})


// ---------------------------------------------------------------------------
// BL-20260906-15: a matter's ranking boost is a bias, so it is shown
// ---------------------------------------------------------------------------

describe('AnalysisStudio ranking boost', () => {
  async function renderWithRetrieval(retrieval: Record<string, unknown>) {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(
          fullResponse({
            irac: { ...fullResponse().irac, retrieval },
          }),
        ),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
  }

  it('names the boost and where it came from', async () => {
    await renderWithRetrieval({
      queries: ['premises liability'],
      result_count: 5,
      boosted_count: 2,
      boost_source: 'matter:acme-v-roe',
    })
    const row = screen.getByTestId('retrieval-boost')
    expect(row).toHaveTextContent('2 passage(s) promoted')
    expect(row).toHaveTextContent('matter:acme-v-roe')
  })

  it('says nothing when no boost was applied', async () => {
    await renderWithRetrieval({
      queries: ['premises liability'],
      result_count: 5,
      boosted_count: 0,
      boost_source: '',
    })
    expect(screen.queryByTestId('retrieval-boost')).not.toBeInTheDocument()
  })
})


// ---------------------------------------------------------------------------
// BL-20260906-10: `trace_url` supersedes `phoenix_trace_url`
// ---------------------------------------------------------------------------

describe('AnalysisStudio trace link', () => {
  async function renderWith(overrides: Record<string, unknown>) {
    server.use(
      http.post('http://localhost:8000/api/analysis', async () =>
        HttpResponse.json(fullResponse(overrides)),
      ),
    )
    render(<AnalysisStudio />)
    fireEvent.click(screen.getByRole('button', { name: /Load sample/i }))
    fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
  }

  it('prefers trace_url', async () => {
    await renderWith({
      trace_url: 'https://collector.test/traces/new',
      phoenix_trace_url: 'https://collector.test/traces/old',
    })
    const link = screen.getByRole('link', {
      name: 'https://collector.test/traces/new',
    })
    expect(link).toHaveAttribute('href', 'https://collector.test/traces/new')
  })

  it('still follows the deprecated spelling on its own', async () => {
    await renderWith({ phoenix_trace_url: 'https://collector.test/traces/old' })
    expect(
      screen.getByRole('link', { name: 'https://collector.test/traces/old' }),
    ).toBeInTheDocument()
  })
})
