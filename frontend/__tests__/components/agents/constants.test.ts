/**
 * The poll cadences the dashboard runs on (BL-20260830-02). Values, not
 * behaviour — but the push fallback only makes sense while the slow cadence
 * is genuinely slower than the fast one, which is what this pins.
 */
import {
  FALLBACK_POLL_MS,
  GAP_ROWS,
  POLL_MS,
} from '@/components/agents/constants'
import { describe, expect, it } from 'vitest'

describe('agents/constants', () => {
  it('polls slower once the push channel is live', () => {
    expect(POLL_MS).toBeGreaterThan(0)
    expect(FALLBACK_POLL_MS).toBeGreaterThan(POLL_MS)
    expect(GAP_ROWS).toBeGreaterThanOrEqual(1)
  })
})
