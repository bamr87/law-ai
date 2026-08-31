import { describe, expect, it } from 'vitest'

import {
  averageSecondsPerQuestion,
  formatClock,
  LSAT_SECTION_SECONDS,
  secondsPerQuestion,
} from '@/lib/lsatTimer'

describe('formatClock', () => {
  it('formats minutes and seconds', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(84)).toBe('1:24')
    expect(formatClock(LSAT_SECTION_SECONDS)).toBe('35:00')
  })

  it('floors fractional seconds and clamps negatives', () => {
    expect(formatClock(1.9)).toBe('0:01')
    expect(formatClock(-12)).toBe('0:00')
  })

  it('includes hours past 60 minutes', () => {
    expect(formatClock(3600)).toBe('1:00:00')
    expect(formatClock(3661)).toBe('1:01:01')
  })
})

describe('secondsPerQuestion', () => {
  it('splits remaining time across remaining items', () => {
    expect(secondsPerQuestion(2100, 25)).toBe(84)
  })

  it('is undefined when no items or no time remain', () => {
    expect(secondsPerQuestion(120, 0)).toBeNull()
    expect(secondsPerQuestion(0, 5)).toBeNull()
    expect(secondsPerQuestion(-1, 5)).toBeNull()
  })
})

describe('averageSecondsPerQuestion', () => {
  it('is the mean time after each answer', () => {
    expect(averageSecondsPerQuestion(90, 1)).toBe(90)
    expect(averageSecondsPerQuestion(168, 2)).toBe(84)
  })

  it('is undefined before the first answer', () => {
    expect(averageSecondsPerQuestion(10, 0)).toBeNull()
  })
})
