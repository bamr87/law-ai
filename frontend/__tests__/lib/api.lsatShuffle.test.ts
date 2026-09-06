/** The shuffle token's path through the API client (BL-20260606-01). */
import { describe, expect, it } from 'vitest'

import { fetchLsatGuide, fetchLsatQuestions, gradeLsat } from '@/lib/api'
import { server } from '@/mocks/server'
import { http, HttpResponse } from 'msw'

describe('per-attempt shuffling', () => {
  it('asks for a shuffled serve only when told to', async () => {
    const urls: string[] = []
    server.use(
      http.get('http://localhost:8000/api/lsat/questions', ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json({ questions: [], count: 0 })
      }),
    )
    await fetchLsatQuestions({ limit: 1, shuffle: true })
    await fetchLsatQuestions({ limit: 1 })
    expect(urls[0]).toContain('shuffle=1')
    expect(urls[1]).not.toContain('shuffle')
  })

  it('echoes the serve token back when grading', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('http://localhost:8000/api/lsat/grade', async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({
          question_id: 'lg-001',
          correct: true,
          correct_choice: 'B',
          explanation: 'Because.',
          section: 'LG',
          concepts: [],
        })
      }),
    )
    await gradeLsat('lg-001', 'B', 0, '20431.abcdef0123456789')
    await gradeLsat('lg-001', 'B')
    expect(bodies[0]).toMatchObject({ remap: '20431.abcdef0123456789' })
    expect(bodies[1]).not.toHaveProperty('remap')
  })

  it('fetches the solve guide under the same permutation', async () => {
    const urls: string[] = []
    server.use(
      http.get(
        'http://localhost:8000/api/lsat/questions/:id/guide',
        ({ request }) => {
          urls.push(request.url)
          return HttpResponse.json({
            question_id: 'lg-001',
            step_count: 0,
            steps: [],
          })
        },
      ),
    )
    await fetchLsatGuide('lg-001', { spoilers: true, remap: '20431.deadbeef' })
    await fetchLsatGuide('lg-001')
    expect(urls[0]).toContain('remap=20431.deadbeef')
    expect(urls[0]).toContain('spoilers=1')
    expect(urls[1]).not.toContain('remap')
  })
})
