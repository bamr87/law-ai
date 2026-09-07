/** Smoke test for the run list row + type tabs (BL-20260830-02). */
import { RunRow, RunTypeTabs } from '@/components/agents/RunRow'
import type { AgentRun } from '@/lib/api'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const run = {
  trace_id: 't-1',
  agent: 'LegalAnalyst',
  type: 'agent_call',
  timestamp: '2026-04-29T12:00:00Z',
  latency_ms: 42,
} as unknown as AgentRun

describe('agents/RunRow', () => {
  it('expands to show the payload and drills into a trace', () => {
    const onDrill = vi.fn()
    render(
      <ul>
        <RunRow run={run} onDrill={onDrill} />
      </ul>,
    )
    fireEvent.click(screen.getByLabelText('Show run details'))
    fireEvent.click(
      screen.getByRole('button', { name: /View all related events/ }),
    )
    expect(onDrill).toHaveBeenCalledWith('t-1')
  })

  it('counts each event type in the filter tabs', () => {
    const onChange = vi.fn()
    render(<RunTypeTabs runs={[run]} active="all" onChange={onChange} />)
    // Labels are humanised ("agent_call" renders as "agent call 1").
    fireEvent.click(screen.getByRole('button', { name: /agent call\s*1/ }))
    expect(onChange).toHaveBeenCalledWith('agent_call')
  })
})
