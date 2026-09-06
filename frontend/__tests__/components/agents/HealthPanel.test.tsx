/** Smoke test for the system-health row (BL-20260830-02). */
import HealthPanel from '@/components/agents/HealthPanel'
import type { LocalAIHealth } from '@/lib/api'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

const health = {
  llm_chain: [
    {
      provider: 'claude_code',
      position: 1,
      configured: true,
      reachable: true,
      model: 'opus',
    },
  ],
  ollama: { reachable: false, models: [], error: 'connection refused' },
  checkpointer: { kind: 'postgres', reachable: true },
  phoenix: { enabled: false, reachable: false, ui_url: '' },
} as unknown as LocalAIHealth

describe('agents/HealthPanel', () => {
  it('names the tier that will serve the next request', () => {
    render(<HealthPanel loading={false} error={null} health={health} />)
    expect(screen.getByText('1. claude_code')).toBeInTheDocument()
    expect(screen.getByText(/serving/)).toBeInTheDocument()
    expect(screen.getByText('connection refused')).toBeInTheDocument()
  })

  it('renders nothing when the probe itself failed', () => {
    const { container } = render(
      <HealthPanel loading={false} error="boom" health={null} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
