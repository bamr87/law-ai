import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StatsPanel from '@/components/lsat/StatsPanel'

describe('StatsPanel', () => {
  it('shows the session beside the all-time totals', () => {
    render(
      <StatsPanel
        session={{ attempts: 4, correct: 3, assisted: 1 }}
        stats={{ attempts: 50, correct: 30, accuracy: 0.6 }}
      />,
    )
    expect(screen.getByText('This session')).toBeInTheDocument()
    expect(screen.getByText('All-time (audit log)')).toBeInTheDocument()
    // Distinct fixtures per card, so each percentage proves which card rendered it.
    expect(screen.getByText('75% accuracy')).toBeInTheDocument()
    expect(screen.getByText('60% accuracy')).toBeInTheDocument()
    expect(screen.queryByText('By section')).not.toBeInTheDocument()
  })

  it('breaks the audit totals down by section when the API has them', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 10,
          correct: 5,
          accuracy: 0.5,
          by_section: {
            LR: { attempts: 6, correct: 3, accuracy: 0.5 },
            RC: { attempts: 4, correct: 2, accuracy: 0.5 },
          },
        }}
      />,
    )
    expect(screen.getByText('By section')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('LR')).toBeInTheDocument()
    expect(screen.getByText('RC')).toBeInTheDocument()
    expect(screen.getAllByText('50%')).toHaveLength(2)
  })

  it('renders zeros rather than crashing before stats arrive', () => {
    render(
      <StatsPanel session={{ attempts: 0, correct: 0, assisted: 0 }} stats={null} />,
    )
    expect(screen.getAllByText('0% accuracy')).toHaveLength(2)
  })
})
