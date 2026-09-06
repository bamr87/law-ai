import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import TutorPane from '@/components/lsat/TutorPane'
import { server } from '@/mocks/server'

const base = {
  question_id: 'lr-001',
  user_choice: 'A',
  correct_choice: 'C',
  is_correct: false,
  explanation: 'Hasty generalisation.',
  coaching: 'Walkthrough — the inductive leap is the flaw.',
  next_steps: ['Review sampling bias'],
  concepts: [
    {
      id: 'flaw-in-reasoning',
      name: 'Flaw in reasoning',
      sections: ['LR'],
      summary: 'Identify the logical defect.',
      detail: null,
      examples: [],
      see_also: [],
      references: [],
    },
  ],
  references: [],
  confidence: 0.85,
  requires_human_review: false,
  latency_ms: 120,
}

describe('TutorPane', () => {
  it('asks on open and names the model that answered', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...base,
          model: 'mistral:7b-instruct-q4_K_M',
          used_llm: true,
          cached: false,
        })
      }),
    )
    render(
      <TutorPane
        questionId="lr-001"
        userChoice="A"
        initialQuestion="Walk me through it."
      />,
    )
    expect(
      await screen.findByText(/Walkthrough — the inductive leap/),
    ).toBeInTheDocument()
    expect(body).toMatchObject({
      question_id: 'lr-001',
      user_choice: 'A',
      user_question: 'Walk me through it.',
    })
    expect(screen.getByText(/mistral:7b-instruct-q4_K_M/)).toBeInTheDocument()
    expect(screen.getByText('Flaw in reasoning')).toBeInTheDocument()
    expect(screen.queryByText(/offline fallback/)).not.toBeInTheDocument()
  })

  it('labels a fallback answer as offline instead of naming a model', async () => {
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', () =>
        HttpResponse.json({
          ...base,
          model: 'fallback/offline',
          used_llm: false,
          cached: false,
          confidence: 0.55,
        }),
      ),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    expect(await screen.findByText(/offline fallback/)).toBeInTheDocument()
    expect(screen.getByText(/55% conf/)).toBeInTheDocument()
    expect(screen.queryByText(/fallback\/offline/)).not.toBeInTheDocument()
  })

  it('offers Regenerate only for a saved walkthrough (spec 045 FR-13)', async () => {
    let refreshed: unknown = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        const b = (await request.json()) as { refresh?: boolean }
        refreshed = b.refresh
        return HttpResponse.json({
          ...base,
          model: 'claude',
          used_llm: true,
          cached: true,
        })
      }),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    expect(await screen.findByText(/saved walkthrough/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Regenerate/ }))
    await screen.findByText(/saved walkthrough/)
    expect(refreshed).toBe(true)
  })
})
