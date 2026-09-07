/** Smoke test for the registry card (BL-20260830-02). */
import AgentCard, { AGENT_DESCRIPTIONS } from '@/components/agents/AgentCard'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

describe('agents/AgentCard', () => {
  it('describes the agent and launches it', () => {
    const onLaunch = vi.fn()
    render(
      <ul>
        <AgentCard
          agent={{ name: 'LegalAnalyst', module: 'law_ai.x' }}
          onLaunch={onLaunch}
        />
      </ul>,
    )
    expect(screen.getByText('LegalAnalyst')).toBeInTheDocument()
    expect(
      screen.getByText(AGENT_DESCRIPTIONS.LegalAnalyst),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    expect(onLaunch).toHaveBeenCalled()
  })
})
