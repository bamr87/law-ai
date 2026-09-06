import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import AuthoringPanel from '@/components/lsat/AuthoringPanel'
import { server } from '@/mocks/server'

const questionProposal = {
  id: 'prop-q-1',
  status: 'pending',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  proposal_kind: 'question',
  section: 'LR',
  difficulty: 'med',
  agent_trace_id: 'trace-1',
  model: 'claude',
  confidence: 0.8,
  source_concept_ids: ['flaw-in-reasoning'],
  draft: {
    section: 'LR',
    difficulty: 'med',
    stem: 'Drafted stem about swans.',
    choices: [
      { label: 'A', text: 'Alpha' },
      { label: 'B', text: 'Bravo' },
    ],
    correct: 'B',
    explanation: 'Because B.',
    concepts: ['flaw-in-reasoning'],
    confidence: 0.8,
  },
}

const guideProposal = {
  ...questionProposal,
  id: 'prop-g-1',
  proposal_kind: 'guide',
  draft: {
    question_id: 'lr-001',
    method: 'Negate the conclusion first.',
    version: 1,
    source: 'author',
    steps: [
      { kind: 'orient', title: 'Find the claim', text: 'Read the last line.', spoiler: false },
      { kind: 'answer', title: 'Pick B', text: 'B negates it.', spoiler: true },
    ],
  },
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/proposals', () =>
      HttpResponse.json({
        proposals: [questionProposal, guideProposal],
        count: 2,
        status: 'pending',
      }),
    ),
    http.get('http://localhost:8000/api/lsat/gaps', () =>
      HttpResponse.json({
        gaps: [
          { section: 'LR', concept: 'flaw-in-reasoning', attempts: 9, correct: 3, accuracy: 0.33 },
        ],
        count: 1,
        limit: 10,
      }),
    ),
    http.post('http://localhost:8000/api/lsat/proposals/:id/approve', ({ params }) =>
      HttpResponse.json({ ...questionProposal, id: params.id, status: 'approved' }),
    ),
    http.post('http://localhost:8000/api/lsat/proposals/:id/reject', ({ params }) =>
      HttpResponse.json({ ...questionProposal, id: params.id, status: 'rejected' }),
    ),
  )
})

describe('AuthoringPanel', () => {
  it('lists pending question and guide drafts with the weakest concepts', async () => {
    render(<AuthoringPanel />)
    expect(await screen.findByText('Pending review (2)')).toBeInTheDocument()
    expect(screen.getByText('Drafted stem about swans.')).toBeInTheDocument()
    expect(screen.getByText('solve guide')).toBeInTheDocument()
    expect(screen.getByText('Negate the conclusion first.')).toBeInTheDocument()
    expect(screen.getByText('Weakest measured concepts')).toBeInTheDocument()
    expect(screen.getByText('33%')).toBeInTheDocument()
  })

  it('drops a draft from the queue once it is approved', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (2)')
    fireEvent.click(screen.getByRole('button', { name: /Approve & promote/ }))
    await waitFor(() =>
      expect(screen.getByText('Pending review (1)')).toBeInTheDocument(),
    )
    expect(screen.queryByText('Drafted stem about swans.')).not.toBeInTheDocument()
    expect(screen.getByText('solve guide')).toBeInTheDocument()
  })

  it('drops a draft from the queue once it is rejected', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (2)')
    fireEvent.click(screen.getAllByRole('button', { name: /^Reject$/ })[1])
    await waitFor(() =>
      expect(screen.getByText('Pending review (1)')).toBeInTheDocument(),
    )
    expect(screen.queryByText('solve guide')).not.toBeInTheDocument()
  })
})
