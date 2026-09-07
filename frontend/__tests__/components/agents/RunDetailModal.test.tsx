/** Smoke test for the provenance drill-in (BL-20260830-02). */
import RunDetailModal from '@/components/agents/RunDetailModal'
import { server } from '@/mocks/server'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

describe('agents/RunDetailModal', () => {
  it('loads the trace and closes on Escape', async () => {
    server.use(
      http.get('http://localhost:8000/api/agents/runs/t-1', () =>
        HttpResponse.json({
          trace_id: 't-1',
          count: 1,
          events: [
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
    )
    const onClose = vi.fn()
    render(<RunDetailModal traceId="t-1" onClose={onClose} />)
    const dialog = screen.getByRole('dialog', { name: 'Run details' })
    await waitFor(() => expect(dialog).toHaveTextContent('LegalAnalyst'))
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
