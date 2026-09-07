/**
 * What the header does on a page too short to scroll (BL-20260906-61).
 *
 * `hidden` is gated on scrolling past HIDE_AFTER_PX, so on a short view —
 * Overview at 390px is the one that prompted this — the reader can reach the
 * bottom without ever crossing that line, and the header stays `condensed`
 * forever. That is the intended answer (there is nothing below to make room
 * for), but until now nothing said so either way, so a future tweak to the
 * threshold could quietly turn "never hides here" into "hides on the first
 * flick" with no test noticing.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

/** Mirrors HIDE_AFTER_PX in app/page.tsx. */
const HIDE_AFTER_PX = 220

function header(): HTMLElement {
  return screen.getByRole('banner')
}

function scrollTo(y: number): void {
  Object.defineProperty(window, 'scrollY', { value: y, configurable: true })
  fireEvent.scroll(window)
}

describe('the header on a page with little to scroll', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('condenses but never hides when the whole page fits above the threshold', () => {
    render(<Page />)
    expect(header().className).toContain('site-header-top')

    // Walk to the bottom of a document that is only HIDE_AFTER_PX tall. Every
    // step is downward and past AT_TOP_PX, so this is the most the reader can
    // possibly do on such a page.
    for (const y of [40, 100, 160, HIDE_AFTER_PX]) {
      act(() => scrollTo(y))
      expect(header().className).toContain('site-header-condensed')
      expect(header().className).not.toContain('site-header-hidden')
    }
  })

  it('hides on the first scroll past the threshold, once the page is tall enough', () => {
    render(<Page />)
    act(() => scrollTo(HIDE_AFTER_PX + 1))
    expect(header().className).toContain('site-header-hidden')
  })

  it('comes back at the top of a short page', () => {
    render(<Page />)
    act(() => scrollTo(160))
    expect(header().className).toContain('site-header-condensed')
    act(() => scrollTo(0))
    expect(header().className).toContain('site-header-top')
  })
})
