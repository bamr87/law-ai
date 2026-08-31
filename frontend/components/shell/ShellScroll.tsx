'use client'

import { recallScroll, rememberScroll } from '@/lib/shell/scrollMemory'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'

/**
 * Scroll state for the shell's single content region.
 *
 * The shell locks the viewport (`h-dvh` + `overflow-hidden`) so the chrome —
 * masthead, rail, sidebar, inspector — is structurally unable to scroll away.
 * The cost of that is that `window.scrollY` is always 0, so anything that
 * used to react to page scroll has to read it from here instead.
 */
export interface ShellScrollState {
  /** Main region has scrolled past the condense threshold. */
  scrolled: boolean
  scrollTop: number
  scrollToTop: () => void
}

/** Distance before a page header condenses. Small enough to feel immediate,
 * large enough that a trackpad twitch doesn't flicker the header. */
export const CONDENSE_AT = 24

const noop = () => {}

const ShellScrollContext = createContext<ShellScrollState>({
  scrolled: false,
  scrollTop: 0,
  scrollToTop: noop,
})

export const ShellScrollProvider = ShellScrollContext.Provider

/**
 * Read shell scroll state. Safe outside the shell — the default context makes
 * a standalone `PageLayout` render in its un-condensed form, which is what a
 * unit test or a Storybook-less preview wants anyway.
 */
export function useShellScroll(): ShellScrollState {
  return useContext(ShellScrollContext)
}

/**
 * Owns the main region's scroll: tracks offset, restores the previous
 * position per route, and exposes a scroll-to-top.
 *
 * `routeKey` is the pathname. Panel query params are deliberately excluded —
 * opening the inspector is not a navigation and must not scroll the reader
 * back to the top of a brief.
 *
 * The element arrives through a **callback ref**, not a ref object handed back
 * to the caller: a ref object would have to be read during render to attach
 * it, and it lets the hook react to the node actually mounting.
 */
export function useMainScrollController(routeKey: string): {
  state: ShellScrollState
  mainRef: (node: HTMLElement | null) => void
} {
  // A ref, not state: the node is a mutable DOM handle the effects below
  // write to (`scrollTop`), and React's compiler rules — rightly — treat a
  // state value as immutable. `<main>` is rendered unconditionally, so the
  // callback ref has always run by the time an effect reads this.
  const nodeRef = useRef<HTMLElement | null>(null)
  const routeRef = useRef(routeKey)
  const [scrollTop, setScrollTop] = useState(0)

  const mainRef = useCallback((el: HTMLElement | null) => {
    nodeRef.current = el
  }, [])

  // Layout effect: restore before paint so the user never sees the top of the
  // page flash by on the way back to where they were.
  useLayoutEffect(() => {
    routeRef.current = routeKey
    const el = nodeRef.current
    if (!el) return
    const top = recallScroll(routeKey)
    el.scrollTop = top
    setScrollTop(top)
  }, [routeKey])

  useEffect(() => {
    const el = nodeRef.current
    if (!el) return
    let frame = 0
    const onScroll = () => {
      // Coalesce to one read per frame: scroll fires far faster than React
      // can usefully re-render, and every handler here touches storage.
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const top = el.scrollTop
        setScrollTop(top)
        rememberScroll(routeRef.current, top)
      })
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      el.removeEventListener('scroll', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  const scrollToTop = useCallback(() => {
    const el = nodeRef.current
    if (!el) return
    // jsdom (and older engines) have no Element.scrollTo; the assignment is
    // the universally supported path and is what the test asserts on.
    if (typeof el.scrollTo === 'function') el.scrollTo({ top: 0 })
    else el.scrollTop = 0
    setScrollTop(0)
    rememberScroll(routeRef.current, 0)
  }, [])

  return {
    state: { scrolled: scrollTop > CONDENSE_AT, scrollTop, scrollToTop },
    mainRef,
  }
}
