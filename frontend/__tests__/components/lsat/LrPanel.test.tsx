import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import LrPanel from '@/components/lsat/LrPanel'
import { server } from '@/mocks/server'

const question = {
  id: 'lr-001',
  section: 'LR',
  type: 'LR',
  difficulty: 'med',
  stem: 'All swans observed are white. Therefore all swans are white.',
  choices: [
    { label: 'A', text: 'Alpha' },
    { label: 'B', text: 'Bravo' },
    { label: 'C', text: 'Charlie' },
  ],
  concepts: [],
  references: [],
  passage_id: null,
}

let requested: string[] = []

beforeEach(() => {
  requested = []
  server.use(
    http.get('http://localhost:8000/api/lsat/questions', ({ request }) => {
      requested.push(new URL(request.url).search)
      return HttpResponse.json({ count: 1, questions: [question] })
    }),
  )
})

describe('LrPanel', () => {
  it('draws one LR question and shows the difficulty toolbar', async () => {
    render(<LrPanel onAttempt={() => {}} />)
    expect(await screen.findByText(/All swans observed/)).toBeInTheDocument()
    expect(screen.getByLabelText('Difficulty')).toHaveValue('any')
    expect(screen.getByText(/Section: Logical Reasoning/)).toBeInTheDocument()
    expect(requested[0]).toContain('section=LR')
    expect(requested[0]).not.toContain('difficulty=')
  })

  it('reloads with the chosen difficulty', async () => {
    render(<LrPanel onAttempt={() => {}} />)
    await screen.findByText(/All swans observed/)
    fireEvent.change(screen.getByLabelText('Difficulty'), {
      target: { value: 'hard' },
    })
    await waitFor(() => expect(requested).toHaveLength(2))
    expect(requested[1]).toContain('difficulty=hard')
  })

  it('surfaces a load failure with a retry', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/questions', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<LrPanel onAttempt={() => {}} />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
  })
})
