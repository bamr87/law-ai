/**
 * The IRAC wait, made visible (BL-20260905-11).
 *
 * `/api/analysis` runs the slowest interactive call in the product — live xAI
 * runs measured 56-103s on real questions — and until the analyst started
 * relaying its deltas the page showed nothing at all between "Run analysis"
 * and the finished result. These tests pin the visible half of that fix: an
 * `analysis_token` event has to reach the live trace panel while the request
 * is still in flight.
 *
 * The socket is mocked rather than served: `openAgentStream` is the seam the
 * component talks to, and driving it directly is what lets a test emit a
 * delta mid-request.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import AnalysisStudio from '@/components/AnalysisStudio'
import type { AgentStreamEvent } from '@/lib/agentStream'
import { server } from '@/mocks/server'

const handlers: ((event: AgentStreamEvent) => void)[] = []
/** The `onStatus` callbacks the component registered (BL-20260905-79). */
const statuses: ((status: 'live' | 'reconnecting' | 'lost') => void)[] = []

vi.mock('@/lib/agentStream', () => ({
  newStreamId: () => 'run-test',
  openAgentStream: (
    _id: string,
    onEvent: (event: AgentStreamEvent) => void,
    options?: { onStatus?: (status: 'live' | 'reconnecting' | 'lost') => void },
  ) => {
    handlers.push(onEvent)
    if (options?.onStatus) statuses.push(options.onStatus)
    return Promise.resolve({ close: () => {} } as unknown as WebSocket)
  },
}))

/** Hold the POST open so the component stays in its "submitting" state. */
function pendingAnalysis(): { release: () => void } {
  let release = () => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.post('http://localhost:8000/api/analysis', async () => {
      await gate
      return HttpResponse.json({
        id: 'an-abc123',
        timestamp: '2026-09-06T00:00:00+00:00',
        latency_ms: 60000,
        confidence: 0.8,
        requires_human_review: false,
        irac: {
          issue: 'i',
          rule: 'r',
          application: 'a',
          conclusion: 'c',
          sources: [],
          confidence: 0.8,
        },
        precedents: { precedents: [], summary: 's', confidence: 0.8 },
        agent_trace: [],
      })
    }),
  )
  return { release }
}

async function startAnalysis(): Promise<{ release: () => void }> {
  const gate = pendingAnalysis()
  handlers.length = 0
  statuses.length = 0
  render(<AnalysisStudio />)
  fireEvent.change(screen.getByLabelText(/Fact pattern/i), {
    target: { value: 'Is a clickwrap arbitration clause enforceable?' },
  })
  fireEvent.click(screen.getByRole('button', { name: /Run analysis/i }))
  await waitFor(() => expect(handlers.length).toBe(1))
  return gate
}

describe('AnalysisStudio live IRAC progress', () => {
  it('shows the analyst writing while the request is still open', async () => {
    const gate = await startAnalysis()

    handlers[0]({
      type: 'analysis_token',
      agent: 'LegalAnalyst',
      text: '{"issue": "clickwrap',
      chars: 20,
      model: 'xai/grok-4.6',
    })

    const line = await screen.findByTestId('analysis-writing')
    expect(line).toHaveTextContent('LegalAnalyst')
    expect(line).toHaveTextContent('writing… 20 characters')
    expect(line).toHaveTextContent('xai/grok-4.6')

    // A second delta replaces the count rather than stacking a second line.
    handlers[0]({
      type: 'analysis_token',
      agent: 'LegalAnalyst',
      text: ' clause"',
      chars: 28,
      model: 'xai/grok-4.6',
    })
    await waitFor(() =>
      expect(screen.getByTestId('analysis-writing')).toHaveTextContent(
        'writing… 28 characters',
      ),
    )
    gate.release()
  })

  it('drops the writing line once that agent reports its step', async () => {
    const gate = await startAnalysis()

    handlers[0]({
      type: 'analysis_token',
      agent: 'LegalAnalyst',
      text: 'partial',
      chars: 7,
    })
    expect(await screen.findByTestId('analysis-writing')).toBeInTheDocument()

    handlers[0]({
      type: 'agent_step',
      agent: 'LegalAnalyst',
      analysis_id: 'an-abc123',
      trace_id: 'trace-1',
      latency_ms: 61000,
      confidence: 0.8,
    })
    await waitFor(() =>
      expect(screen.queryByTestId('analysis-writing')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('LegalAnalyst')).toBeInTheDocument()
    gate.release()
  })

  it('keeps the finished step list on screen after the result lands', async () => {
    // BL-20260905-22: on the degraded path the REST response can land a few
    // hundred milliseconds after the first step event. Unmounting the panel
    // with `submitting` threw the streamed detail away before it could be
    // read; it now survives the run that produced it.
    const gate = await startAnalysis()

    handlers[0]({
      type: 'agent_step',
      agent: 'PrecedentHunter',
      analysis_id: 'an-abc123',
      trace_id: 'trace-2',
      latency_ms: 120,
      confidence: 0.8,
      degraded: true,
    })
    expect(
      await screen.findByRole('heading', { name: /Agents reporting/i }),
    ).toBeInTheDocument()

    gate.release()
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )

    // The run is over, but its trace is still readable beside the result.
    expect(
      screen.getByRole('heading', { name: /Agents reported/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('PrecedentHunter')).toBeInTheDocument()
    expect(screen.getByText(/degraded — no engine ran/)).toBeInTheDocument()
  })

  // BL-20260905-79: a dropped socket froze the trace with no explanation,
  // which reads as a stalled analysis rather than a lost connection.
  it('says the live trace is reconnecting, then that it is gone', async () => {
    const gate = await startAnalysis()
    expect(statuses).toHaveLength(1)

    statuses[0]('reconnecting')
    expect(await screen.findByText('Reconnecting…')).toBeInTheDocument()

    // A reconnect that took clears the notice.
    statuses[0]('live')
    await waitFor(() =>
      expect(screen.queryByText('Reconnecting…')).not.toBeInTheDocument(),
    )

    // Retries spent: say so rather than promising a reconnect that will not
    // come. The REST response is still on its way.
    statuses[0]('lost')
    expect(
      await screen.findByText(/Live trace disconnected/),
    ).toBeInTheDocument()

    gate.release()
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /IRAC Brief/i }),
      ).toBeInTheDocument(),
    )
    // The connection notice belongs to the run, not to the result.
    expect(
      screen.queryByText(/Live trace disconnected/),
    ).not.toBeInTheDocument()
  })
})
