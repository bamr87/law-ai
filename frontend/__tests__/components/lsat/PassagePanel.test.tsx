import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import PassagePanel, { PassageReader } from '@/components/lsat/PassagePanel'
import { server } from '@/mocks/server'

const passage = {
  id: 'rc-passage-001',
  section: 'RC' as const,
  title: 'Federal pleading evolution',
  summary: 'Conley → Twombly → Iqbal.',
  passage: 'Long passage text.',
  setup: null,
  rules: [],
  source: 'Test',
}

const question = {
  id: 'rc-001',
  section: 'RC',
  type: 'RC',
  difficulty: 'med',
  stem: 'What is the main point of the passage?',
  choices: [
    { label: 'A', text: 'Alpha' },
    { label: 'B', text: 'Bravo' },
  ],
  concepts: [],
  references: [],
  passage_id: 'rc-passage-001',
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/passages', () =>
      HttpResponse.json({ count: 1, passages: [passage] }),
    ),
    http.get('http://localhost:8000/api/lsat/passages/rc-passage-001', () =>
      HttpResponse.json({ count: 1, passage, questions: [question] }),
    ),
  )
})

describe('PassagePanel', () => {
  it('loads the passage list, then the active passage with its questions', async () => {
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    expect(await screen.findByText(/Long passage text/)).toBeInTheDocument()
    expect(screen.getByLabelText('Passage')).toHaveValue('rc-passage-001')
    expect(screen.getByText(/main point of the passage/)).toBeInTheDocument()
    expect(screen.getByText(/Section: Reading Comprehension/)).toBeInTheDocument()
  })

  it('says so when a section has no passages yet', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/passages', () =>
        HttpResponse.json({ count: 0, passages: [] }),
      ),
    )
    render(<PassagePanel section="LG" onAttempt={() => {}} />)
    expect(
      await screen.findByText(/No logic games passages have been authored yet/),
    ).toBeInTheDocument()
  })
})

describe('PassageReader', () => {
  it('gives a comparative set two headed texts (spec 047 FR-9)', () => {
    render(
      <PassageReader
        passage={{
          ...passage,
          passage_b: 'Second text.',
          title_a: 'First view',
          title_b: 'Second view',
        }}
      />,
    )
    expect(screen.getByText('Comparative passages')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'First view' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Second view' })).toBeInTheDocument()
    expect(screen.getByText('Second text.')).toBeInTheDocument()
  })

  it('renders a game setup with its numbered rules', () => {
    render(
      <PassageReader
        passage={{
          ...passage,
          section: 'LG',
          passage: null,
          setup: 'Six runners finish a race.',
          rules: ['1. K finishes before L', '2. M is not last'],
        }}
      />,
    )
    expect(screen.getByText('Game setup')).toBeInTheDocument()
    expect(screen.getByText('K finishes before L')).toBeInTheDocument()
    expect(screen.getByText('M is not last')).toBeInTheDocument()
  })
})
