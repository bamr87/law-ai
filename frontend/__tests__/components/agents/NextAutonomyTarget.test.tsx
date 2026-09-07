/** Smoke test for the autonomy-target card (BL-20260527-07, BL-20260830-02). */
import NextAutonomyTarget from '@/components/agents/NextAutonomyTarget'
import type { LsatGapRow } from '@/lib/api'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

const gaps = [
  {
    section: 'LR',
    concept: 'necessary-assumption',
    attempts: 12,
    correct: 4,
    accuracy: 0.3333,
  },
] as LsatGapRow[]

describe('agents/NextAutonomyTarget', () => {
  it('names the top gap row', () => {
    render(<NextAutonomyTarget loading={false} error={null} gaps={gaps} />)
    expect(screen.getByText('necessary-assumption')).toBeInTheDocument()
    expect(screen.getByText(/12 attempts/)).toBeInTheDocument()
  })

  it('says so when nothing has been measured', () => {
    render(<NextAutonomyTarget loading={false} error={null} gaps={[]} />)
    expect(screen.getByText(/No measured gaps yet/)).toBeInTheDocument()
  })
})
