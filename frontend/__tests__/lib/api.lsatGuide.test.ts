/** Tests for the solve-guide API client (spec 041 T-006, AC-2). */
import { describe, expect, it } from 'vitest'

import {
  fetchLsatGuide,
  gradeLsat,
  LsatGuideNotFoundError,
} from '@/lib/api'
import { server } from '@/mocks/server'
import { http, HttpResponse } from 'msw'

describe('fetchLsatGuide', () => {
  it('returns spoiler-stripped steps by default', async () => {
    const guide = await fetchLsatGuide('lg-001')
    expect(guide.question_id).toBe('lg-001')
    expect(guide.step_count).toBe(3)
    const last = guide.steps[guide.steps.length - 1]
    expect(last.locked).toBe(true)
    expect(last.spoiler).toBe(true)
    expect(last.text).toBeUndefined()
    expect(guide.steps[0].locked).toBe(false)
    expect(guide.steps[0].representation?.rep_type).toBe('sequence')
  })

  it('returns full steps with spoilers enabled', async () => {
    const guide = await fetchLsatGuide('lg-001', { spoilers: true })
    const last = guide.steps[guide.steps.length - 1]
    expect(last.locked).toBe(false)
    expect(last.text).toContain('D is correct')
  })

  it('throws a typed 404 carrying the tutor fallback flag', async () => {
    const err = await fetchLsatGuide('lr-999').catch((e) => e)
    expect(err).toBeInstanceOf(LsatGuideNotFoundError)
    expect((err as LsatGuideNotFoundError).hasTutor).toBe(true)
  })
})

describe('gradeLsat hints', () => {
  it('sends hints_used only when positive', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('http://localhost:8000/api/lsat/grade', async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({
          question_id: 'lg-001',
          correct: true,
          correct_choice: 'D',
          explanation: 'Because.',
          section: 'LG',
          concepts: [],
        })
      }),
    )
    await gradeLsat('lg-001', 'D', 2)
    await gradeLsat('lg-001', 'D', 0)
    await gradeLsat('lg-001', 'D')
    expect(bodies[0]).toMatchObject({ hints_used: 2 })
    expect(bodies[1]).not.toHaveProperty('hints_used')
    expect(bodies[2]).not.toHaveProperty('hints_used')
  })
})
