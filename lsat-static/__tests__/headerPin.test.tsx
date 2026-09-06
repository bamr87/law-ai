/**
 * Keeping the header where the reader wants it (BL-20260901-05).
 *
 * The site header condenses and hides on scroll direction, which is the right
 * default on a phone but is an answer to a question rather than a fact. This
 * covers the explicit control: it exists, it is a real toggle, the preference
 * survives a reload, and while it is on the header is never taken away.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

const KEY = 'lsat-practice.header-pinned.v1'

function header(): HTMLElement {
  return screen.getByRole('banner')
}

function pin(): HTMLElement {
  return screen.getByRole('button', { name: /header/i })
}

/** Scroll far enough down, fast enough, that the header would hide. */
function scrollDown(to = 600): void {
  Object.defineProperty(window, 'scrollY', { value: to, configurable: true })
  fireEvent.scroll(window)
}

describe('the header pin', () => {
  beforeEach(() => {
    // The scroll handler batches into an animation frame; run it synchronously
    // so a case asserts the header state rather than the scheduling.
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is a toggle that starts unpinned', () => {
    render(<Page />)
    expect(pin()).toHaveAttribute('aria-pressed', 'false')
    expect(pin()).toHaveAccessibleName('Keep the header visible')
    fireEvent.click(pin())
    expect(pin()).toHaveAttribute('aria-pressed', 'true')
    expect(pin()).toHaveAccessibleName('Unpin the header')
  })

  it('remembers the choice on this device', () => {
    const first = render(<Page />)
    fireEvent.click(pin())
    expect(window.localStorage.getItem(KEY)).toBe('1')
    first.unmount()

    render(<Page />)
    expect(pin()).toHaveAttribute('aria-pressed', 'true')
    expect(header().className).toContain('site-header-pinned')
  })

  it('keeps the header on screen while it is pinned', () => {
    render(<Page />)
    // Unpinned, scrolling down past a screenful takes the bar away.
    act(() => scrollDown())
    expect(header().className).toContain('site-header-hidden')

    // Pinning brings it straight back rather than waiting for the next scroll.
    fireEvent.click(pin())
    expect(header().className).not.toContain('site-header-hidden')
    expect(header().className).toContain('site-header-condensed')

    act(() => scrollDown(1200))
    expect(header().className).not.toContain('site-header-hidden')
  })

  it('is reachable from the keyboard, and documented in the ? sheet', () => {
    render(<Page />)
    expect(pin()).toHaveAttribute('aria-keyshortcuts', '.')
    fireEvent.keyDown(window, { key: '.' })
    expect(pin()).toHaveAttribute('aria-pressed', 'true')
    fireEvent.keyDown(window, { key: '.' })
    expect(pin()).toHaveAttribute('aria-pressed', 'false')

    fireEvent.keyDown(window, { key: '?' })
    expect(
      screen.getByText('Keep the header visible, or let it hide on scroll'),
    ).toBeInTheDocument()
  })

  it('survives storage being unavailable', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      render(<Page />)
      expect(pin()).toHaveAttribute('aria-pressed', 'false')
    } finally {
      spy.mockRestore()
    }
  })
})
