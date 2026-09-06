import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

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
