/** Smoke test for the spec lifecycle panel (BL-20260830-02). */
import SpecsPanel from '@/components/agents/SpecsPanel'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

describe('agents/SpecsPanel', () => {
  it('groups specs by status', () => {
    render(
      <SpecsPanel
        loading={false}
        specs={[
          { id: '003-agent-ops-dashboard', status: 'planned' },
          { id: '041-shell-navigation-scroll', status: 'shipped' },
        ]}
      />,
    )
    expect(screen.getByText('003-agent-ops-dashboard')).toBeInTheDocument()
  })

  it('says so when there are no specs', () => {
    render(<SpecsPanel loading={false} specs={[]} />)
    expect(screen.getByText('No specs yet.')).toBeInTheDocument()
  })
})
