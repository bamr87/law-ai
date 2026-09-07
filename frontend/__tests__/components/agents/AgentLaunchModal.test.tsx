/** Smoke test for the launch dialog (BL-20260830-02; trap from BL-20260831-07). */
import AgentLaunchModal from '@/components/agents/AgentLaunchModal'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

describe('agents/AgentLaunchModal', () => {
  it('is a focus-trapped dialog that closes on Escape', async () => {
    const onClose = vi.fn()
    render(
      <AgentLaunchModal
        agent={{ name: 'LegalAnalyst', module: 'law_ai.x' }}
        onClose={onClose}
      />,
    )
    const dialog = screen.getByRole('dialog', { name: /Run LegalAnalyst/ })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    await waitFor(() =>
      expect(dialog).toContainElement(document.activeElement as HTMLElement),
    )
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
