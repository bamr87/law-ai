'use client'

import { useLayoutEffect, type RefObject } from 'react'

/**
 * Publish an element's measured height as a CSS custom property on `<html>`
 * (BL-20260831-20).
 *
 * The sticky stack — site header, drill head, passage column — hangs off
 * `--site-header-h` and `--drill-head-h`, which were measured by hand and
 * written into `globals.css` as rem constants. That works exactly until
 * someone changes the header's content: the number then has to be re-measured
 * by a person who knows it exists, and until they do, every rung below it is
 * off by the difference. This makes the token follow the element instead.
 *
 * The constants stay in the stylesheet as the first-paint fallback. A static
 * export has no JavaScript until hydration, so the very first frame is still
 * drawn against them — they are a fallback now, not the source of truth.
 *
 * Two guards worth keeping:
 *
 *  - `onlyWhen` restricts measuring to the viewports where the tokens are
 *    actually used. Below 820px the header condenses and hides on scroll with
 *    a transform, so writing its animating height into a sticky offset would
 *    make the rungs below it jitter for the length of the transition.
 *  - Writes are batched into an animation frame. A `ResizeObserver` callback
 *    that writes a style the observed subtree depends on is how you get
 *    "ResizeObserver loop completed with undelivered notifications".
 */
export function useMeasuredCssVar(
  ref: RefObject<HTMLElement | null>,
  name: string,
  options: {
    /**
     * Pixels to subtract from the measured height. `--site-header-h` is
     * deliberately a hair under the real height so the rung below tucks by a
     * pixel rather than leaving a gap for content to scroll through.
     */
    tuckPx?: number
    /** Media query the measurement applies to; outside it, the token is left
     * to the stylesheet's constant. */
    onlyWhen?: string
  } = {},
): void {
  const { tuckPx = 0, onlyWhen } = options

  useLayoutEffect(() => {
    const el = ref.current
    // No ResizeObserver: an older browser, or a test environment. The rem
    // constants are still in the stylesheet, so the layout is correct — just
    // not self-correcting.
    if (!el || typeof ResizeObserver === 'undefined') return

    const root = document.documentElement
    const media = onlyWhen ? (window.matchMedia?.(onlyWhen) ?? null) : null
    // `pending` rather than the frame id alone: a synchronous
    // `requestAnimationFrame` (a test stub, a polyfill) runs the callback
    // before the id is assigned, which would otherwise leave the hook looking
    // permanently busy.
    let frame = 0
    let pending = false

    const write = () => {
      pending = false
      frame = 0
      if (media && !media.matches) {
        root.style.removeProperty(name)
        return
      }
      const measured = Math.round(el.getBoundingClientRect().height) - tuckPx
      // A collapsed or not-yet-laid-out element must not zero the offset the
      // whole sticky stack hangs from.
      if (measured > 0) root.style.setProperty(name, `${measured}px`)
    }

    const schedule = () => {
      if (pending) return
      pending = true
      if (typeof window.requestAnimationFrame !== 'function') {
        write()
        return
      }
      frame = window.requestAnimationFrame(write)
    }

    schedule()
    const observer = new ResizeObserver(schedule)
    observer.observe(el)
    media?.addEventListener?.('change', schedule)

    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      observer.disconnect()
      media?.removeEventListener?.('change', schedule)
      // Hand the token back to the stylesheet: an unmounted element cannot
      // keep claiming to be the height of anything.
      root.style.removeProperty(name)
    }
  }, [ref, name, tuckPx, onlyWhen])
}

export default useMeasuredCssVar
