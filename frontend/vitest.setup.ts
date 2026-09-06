import '@testing-library/jest-dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { cleanup, configure } from '@testing-library/react'
import { server } from './mocks/server'

// RTL's async utilities default to a 1s deadline, which is generous on a warm
// laptop and marginal on a loaded CI runner: several `findBy*` calls that
// always pass here have failed in CI purely on timing. testTimeout is already
// 15s, so a longer async deadline cannot hang a run — it only stops a slow
// render from reading as a missing element. A genuinely absent element still
// fails, just later.
configure({ asyncUtilTimeout: 5000 })

// Establish API mocking before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

// Reset handlers after each test
afterEach(() => {
  cleanup()
  server.resetHandlers()
})

// Clean up after all tests
afterAll(() => server.close())