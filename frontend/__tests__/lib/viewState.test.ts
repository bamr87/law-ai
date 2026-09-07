import { describe, expect, it } from 'vitest'
import { readViewParam, VIEW_KEYS, withViewParam } from '@/lib/shell/viewState'
import { PANEL_KEYS } from '@/lib/shell/panels'

/**
 * The URL is a shared namespace: the shell owns the panel keys, screens own
 * the view keys (BL-20260831-02). These are the pure halves of that contract,
 * testable without mounting a screen.
 */
describe('view-state params', () => {
  it('reserves keys that do not collide with the shell’s panel keys', () => {
    for (const key of VIEW_KEYS) {
      expect(PANEL_KEYS).not.toContain(key)
    }
    expect(new Set(VIEW_KEYS).size).toBe(VIEW_KEYS.length)
  })

  it('sets one key and leaves every other alone', () => {
    const params = new URLSearchParams('sidebar=0&inspector=1&q=old')
    const next = new URLSearchParams(withViewParam(params, 'tab', 'RC'))
    expect(next.get('tab')).toBe('RC')
    expect(next.get('sidebar')).toBe('0')
    expect(next.get('inspector')).toBe('1')
    expect(next.get('q')).toBe('old')
    // The source is untouched — callers hold it from `useSearchParams`.
    expect(params.get('tab')).toBeNull()
  })

  it('removes the key for an empty or null value', () => {
    const params = new URLSearchParams('tab=RC&sidebar=0')
    expect(withViewParam(params, 'tab', null)).toBe('sidebar=0')
    expect(withViewParam(params, 'tab', '')).toBe('sidebar=0')
  })

  it('reads a value, and falls back for one outside the allowed set', () => {
    const params = new URLSearchParams('tab=RC&type=agent_call')
    expect(readViewParam(params, 'tab', 'overview', ['overview', 'RC'])).toBe(
      'RC',
    )
    expect(readViewParam(params, 'tab', 'overview', ['overview', 'LR'])).toBe(
      'overview',
    )
    // No allowed set: free text passes through.
    expect(readViewParam(params, 'type', 'all')).toBe('agent_call')
  })

  it('falls back for a missing, empty, or absent-params read', () => {
    expect(readViewParam(new URLSearchParams(), 'q', '')).toBe('')
    expect(readViewParam(new URLSearchParams('q='), 'q', 'x')).toBe('x')
    expect(readViewParam(null, 'case', 'none')).toBe('none')
  })
})
