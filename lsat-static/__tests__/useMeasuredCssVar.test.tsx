/**
 * The sticky stack measures itself (BL-20260831-20).
 *
 * `--site-header-h` and `--drill-head-h` were hand-measured constants: correct
 * until the header's content changed, and then quietly wrong for every rung
 * hanging off them. `useMeasuredCssVar` makes the token follow the element.
 *
 * jsdom has neither `ResizeObserver` nor layout, so both are supplied here —
 * the observer as a minimal stand-in that records what it was told to watch,
 * and the height as a stubbed `getBoundingClientRect`. What is being tested is
 * the hook's contract (when it writes, what it writes, when it declines, and
 * that it cleans up), not the browser's measurement.
 */
import { render } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useMeasuredCssVar } from '@/lib/useMeasuredCssVar'

/** Every observer built during a test, so a case can fire its callback. */
let observers: { callback: () => void; targets: Element[]; disconnected: boolean }[] = []

class FakeResizeObserver {
  private entry: { callback: () => void; targets: Element[]; disconnected: boolean }
  constructor(callback: () => void) {
    this.entry = { callback, targets: [], disconnected: false }
    observers.push(this.entry)
  }
  observe(target: Element): void {
    this.entry.targets.push(target)
  }
  disconnect(): void {
    this.entry.disconnected = true
  }
  unobserve(): void {}
}

function setHeight(px: number): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () => ({ height: px, width: 0, top: 0, left: 0, bottom: px, right: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect,
  )
}

/** matchMedia is stubbed globally in vitest.setup.ts; this varies `matches`. */
function setWide(matches: boolean): void {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  )
}

function Header({
  name = '--site-header-h',
  tuckPx,
  onlyWhen,
}: {
  name?: string
  tuckPx?: number
  onlyWhen?: string
}) {
  const ref = useRef<HTMLElement | null>(null)
  useMeasuredCssVar(ref, name, { tuckPx, onlyWhen })
  return <header ref={ref}>chrome</header>
}

function token(name = '--site-header-h'): string {
  return document.documentElement.style.getPropertyValue(name)
}

describe('useMeasuredCssVar', () => {
  beforeEach(() => {
    observers = []
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)
    // requestAnimationFrame is batched by the hook; run it synchronously so a
    // test asserts the write rather than the scheduling.
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.documentElement.removeAttribute('style')
  })

  it('publishes the measured height as a pixel value', () => {
    setHeight(61)
    render(<Header />)
    expect(token()).toBe('61px')
  })

  it('subtracts the deliberate one-pixel tuck', () => {
    // The rung below has to tuck under the header rather than leave a gap for
    // content to scroll through.
    setHeight(61)
    render(<Header tuckPx={1} />)
    expect(token()).toBe('60px')
  })

  it('re-measures when the element resizes', () => {
    setHeight(61)
    render(<Header />)
    setHeight(101)
    // A wrapped nav row, a longer brand, a new control: the token follows.
    observers[0].callback()
    expect(token()).toBe('101px')
  })

  it('watches the element it was given', () => {
    setHeight(61)
    const { container } = render(<Header />)
    expect(observers[0].targets).toEqual([container.querySelector('header')])
  })

  it('leaves the stylesheet constant alone outside the media query', () => {
    // Below 820px the header condenses and hides on a transform; writing that
    // animating height into a sticky offset would make everything under it
    // jitter for the length of the transition.
    setWide(false)
    setHeight(136)
    render(<Header onlyWhen="(min-width: 820px)" />)
    expect(token()).toBe('')
  })

  it('never zeroes the offset the whole stack hangs from', () => {
    setHeight(0)
    render(<Header />)
    expect(token()).toBe('')
  })

  it('hands the token back to the stylesheet on unmount', () => {
    setHeight(61)
    const view = render(<Header />)
    expect(token()).toBe('61px')
    view.unmount()
    expect(token()).toBe('')
    expect(observers[0].disconnected).toBe(true)
  })

  it('does nothing where ResizeObserver does not exist', () => {
    // An older browser, or a prerender. The rem constants in globals.css are
    // still in force, so the layout is correct — just not self-correcting.
    vi.stubGlobal('ResizeObserver', undefined)
    setHeight(61)
    render(<Header />)
    expect(token()).toBe('')
  })
})
