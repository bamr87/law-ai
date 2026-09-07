/**
 * The hook that keeps a focus trap from re-focusing itself every render
 * (BL-20260831-07, extracted in BL-20260830-02).
 */
import { useStableDismiss } from '@/components/agents/useStableDismiss'
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

describe('agents/useStableDismiss', () => {
  it('keeps one identity while always calling the latest callback', () => {
    const seen: (() => void)[] = []
    function Probe({ onClose }: { onClose: () => void }) {
      seen.push(useStableDismiss(onClose))
      return null
    }
    const first = vi.fn()
    const second = vi.fn()
    const { rerender } = render(<Probe onClose={first} />)
    rerender(<Probe onClose={second} />)

    expect(seen[0]).toBe(seen[1])
    seen[1]()
    expect(second).toHaveBeenCalled()
    expect(first).not.toHaveBeenCalled()
  })
})
