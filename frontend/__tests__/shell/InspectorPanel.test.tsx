import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InspectorPanel from '@/components/shell/InspectorPanel'

vi.mock('next/navigation', () => ({
  usePathname: () => '/analysis',
}))

describe('InspectorPanel', () => {
  it('shows the UPL banner on analysis', () => {
    render(<InspectorPanel />)
    expect(screen.getByText('Not legal advice')).toBeInTheDocument()
    expect(screen.getByText('Analysis Studio')).toBeInTheDocument()
  })
})
