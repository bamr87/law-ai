import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// jsdom implements neither of these, and both are load-bearing on the real
// page: the nav scrolls the current section into view, honouring the reader's
// reduced-motion preference. Stubbed rather than mocked away per test, so a
// component test can render the page itself (BL-20260901-11).
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}
if (typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = () => {}
}

afterEach(() => {
  cleanup()
  // Progress, drafts, and read marks all live in localStorage; a test must
  // never inherit another test's device state.
  try {
    window.localStorage.clear()
  } catch {
    /* storage unavailable in this environment */
  }
})
