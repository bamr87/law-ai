/** Smoke test for the per-agent metrics table (BL-20260830-02). */
import MetricsPanel from '@/components/agents/MetricsPanel'
import type { AgentMetric } from '@/lib/api'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const data = {
  window_size: 500,
  errors_total: 0,
  agents: [
    {
      agent: 'LegalAnalyst',
      count: 4,
      error_count: 0,
      success_rate: 1,
      p50_ms: 100,
      p95_ms: 200,
      avg_confidence: 0.8,
      last_seen: '2026-04-29T12:00:00Z',
      last_trace_id: 't-1',
    } as unknown as AgentMetric,
  ],
}

describe('agents/MetricsPanel', () => {
  it('renders a row per agent', () => {
    render(
      <MetricsPanel
        loading={false}
        error={null}
        data={data}
        onSelectTrace={vi.fn()}
      />,
    )
    expect(screen.getByText('LegalAnalyst')).toBeInTheDocument()
    expect(screen.getByText(/Window: last 500 events/)).toBeInTheDocument()
  })

  it('explains an empty window instead of drawing an empty table', () => {
    render(
      <MetricsPanel
        loading={false}
        error={null}
        data={{ ...data, agents: [] }}
        onSelectTrace={vi.fn()}
      />,
    )
    expect(
      screen.getByText(/No agent calls in the last 500 events/),
    ).toBeInTheDocument()
  })
})
