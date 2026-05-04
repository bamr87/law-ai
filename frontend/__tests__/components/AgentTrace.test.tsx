import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AgentTrace from '@/components/AgentTrace'

describe('AgentTrace', () => {
  it('renders agent steps correctly', () => {
    const trace = ['IngestionScout', 'LegalAnalyst', 'PrecedentHunter']
    render(<AgentTrace steps={trace} />)

    expect(screen.getByText('IngestionScout')).toBeInTheDocument()
    expect(screen.getByText('LegalAnalyst')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('shows confidence score when provided', () => {
    render(<AgentTrace steps={['LegalAnalyst']} confidence={0.92} />)
    expect(screen.getByText(/92%/)).toBeInTheDocument()
  })
})