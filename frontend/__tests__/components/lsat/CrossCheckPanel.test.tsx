/** Tests for the answer cross-check panel (spec 041 FR-14). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import CrossCheckPanel from '@/components/lsat/CrossCheckPanel'

describe('CrossCheckPanel', () => {
  it('reports agreement as corroboration, never as proof', async () => {
    render(<CrossCheckPanel questionId="lg-001" />)
    fireEvent.click(
      screen.getByRole('button', { name: /cross-check this answer/i }),
    )
    await waitFor(() =>
      expect(
        screen.getByText(/independent solve agrees with the answer key/i),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText(/corroboration, not proof/i)).toBeInTheDocument()
    expect(
      screen.getByText('Rules eliminate every other order.'),
    ).toBeInTheDocument()
  })

  it('flags disagreement for human review', async () => {
    render(<CrossCheckPanel questionId="lr-001" />)
    fireEvent.click(
      screen.getByRole('button', { name: /cross-check this answer/i }),
    )
    const flag = await screen.findByRole('alert')
    expect(flag).toHaveTextContent(/disagreement — flagged for human review/i)
    expect(screen.getByText(/blind solve picked/i)).toBeInTheDocument()
  })

  it('is honest when no provider is reachable', async () => {
    render(<CrossCheckPanel questionId="rc-042" />)
    fireEvent.click(
      screen.getByRole('button', { name: /cross-check this answer/i }),
    )
    await waitFor(() =>
      expect(
        screen.getByText(/cross-check unavailable — no model reachable/i),
      ).toBeInTheDocument(),
    )
    expect(screen.queryByText(/blind solve picked/i)).not.toBeInTheDocument()
  })
})
