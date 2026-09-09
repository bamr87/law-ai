import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  getDiagnoseMode,
  resetDiagnoseModeForTests,
  setDiagnoseMode,
  useDiagnoseMode,
} from '@/lib/lsat/diagnoseMode'

afterEach(() => resetDiagnoseModeForTests())

describe('diagnoseMode store (spec 053 FR-10)', () => {
  it('is off by default and persists a turn-on', () => {
    expect(getDiagnoseMode()).toBe(false)
    setDiagnoseMode(true)
    expect(getDiagnoseMode()).toBe(true)
    expect(window.localStorage.getItem('law-ai.lsat.diagnose.v1')).toBe('1')
    setDiagnoseMode(false)
    expect(window.localStorage.getItem('law-ai.lsat.diagnose.v1')).toBeNull()
  })

  it('notifies subscribed components', () => {
    const { result } = renderHook(() => useDiagnoseMode())
    expect(result.current[0]).toBe(false)
    act(() => result.current[1](true))
    expect(result.current[0]).toBe(true)
  })
})
