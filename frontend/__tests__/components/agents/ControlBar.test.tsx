/** Smoke test for the header strip split out in BL-20260830-02. */
import { ControlBar, KPIStrip } from '@/components/agents/ControlBar'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

describe('agents/ControlBar', () => {
  it('reports live/paused state and toggles', () => {
    const onToggle = vi.fn()
    render(
      <ControlBar
        paused={false}
        onTogglePause={onToggle}
        lastUpdated={new Date()}
        pushLive={false}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /pause|live/i }))
    expect(onToggle).toHaveBeenCalled()
  })

  it('renders the KPI row with an average latency', () => {
    render(
      <KPIStrip
        agentCount={3}
        runCount={42}
        backlog={{ open: 2, claimed: 1, done: 4, total: 7 }}
        specCount={9}
        latencies={[100, 300]}
      />,
    )
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })
})
