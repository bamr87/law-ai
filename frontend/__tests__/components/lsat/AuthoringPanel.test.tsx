import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import AuthoringPanel from '@/components/lsat/AuthoringPanel'
import { lsatFactoryStatusFixture, server } from '@/mocks/server'

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

const crossCheckProposal = {
  ...questionProposal,
  id: 'prop-x-1',
  proposal_kind: 'crosscheck',
  draft: {
    question_id: 'lr-002',
    section: 'LR',
    difficulty: 'med',
    stem: 'Cross-checked stem about tides.',
    bank_choice: 'C',
    model_choice: 'E',
    rationale: 'E follows from the second premise.',
    model: 'claude_code/claude-opus-5',
  },
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/proposals', () =>
      HttpResponse.json({
        proposals: [questionProposal, guideProposal, crossCheckProposal],
        count: 3,
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
    expect(await screen.findByText('Pending review (3)')).toBeInTheDocument()
    expect(screen.getByText('Drafted stem about swans.')).toBeInTheDocument()
    expect(screen.getByText('solve guide')).toBeInTheDocument()
    expect(screen.getByText('Negate the conclusion first.')).toBeInTheDocument()
    expect(screen.getByText('Weakest measured concepts')).toBeInTheDocument()
    expect(screen.getByText('33%')).toBeInTheDocument()
  })

  it('drops a draft from the queue once it is approved', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (3)')
    fireEvent.click(screen.getByRole('button', { name: /Approve & promote/ }))
    await waitFor(() =>
      expect(screen.getByText('Pending review (2)')).toBeInTheDocument(),
    )
    expect(screen.queryByText('Drafted stem about swans.')).not.toBeInTheDocument()
    expect(screen.getByText('solve guide')).toBeInTheDocument()
  })

  it('drops a draft from the queue once it is rejected', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (3)')
    fireEvent.click(screen.getAllByRole('button', { name: /^Reject$/ })[1])
    await waitFor(() =>
      expect(screen.getByText('Pending review (2)')).toBeInTheDocument(),
    )
    expect(screen.queryByText('solve guide')).not.toBeInTheDocument()
  })

  it('renders a cross-check disagreement as a report, not a draft', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (3)')
    expect(screen.getByText('cross-check')).toBeInTheDocument()
    expect(screen.getByText('lr-002')).toBeInTheDocument()
    expect(screen.getByText('Cross-checked stem about tides.')).toBeInTheDocument()
    // Its buttons say what approving actually means: no content is written.
    expect(screen.getByRole('button', { name: 'Key verified' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Key is wrong' })).toBeInTheDocument()
  })

  it('drops a cross-check row once the key is confirmed', async () => {
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (3)')
    fireEvent.click(screen.getByRole('button', { name: 'Key verified' }))
    await waitFor(() =>
      expect(screen.getByText('Pending review (2)')).toBeInTheDocument(),
    )
    expect(screen.queryByText('cross-check')).not.toBeInTheDocument()
  })

  // BL-20260830-14: the guide-proposal card exists because the question-shaped
  // `ProposalCard` crashed on a guide draft, and the approve → serve path was
  // covered only at the API layer. These pin the card itself.
  describe('guide proposal card', () => {
    it('renders the guide draft in full, beside the question card', async () => {
      render(<AuthoringPanel />)
      await screen.findByText('Pending review (3)')

      // Kind, the question it belongs to, and the method.
      expect(screen.getByText('solve guide')).toBeInTheDocument()
      expect(screen.getByText('lr-001')).toBeInTheDocument()
      expect(screen.getByText('Negate the conclusion first.')).toBeInTheDocument()

      // Every step, with its kind, title and body.
      expect(screen.getByText('orient')).toBeInTheDocument()
      expect(screen.getByText('Find the claim')).toBeInTheDocument()
      expect(screen.getByText('Read the last line.')).toBeInTheDocument()
      expect(screen.getByText('answer')).toBeInTheDocument()
      expect(screen.getByText('Pick B')).toBeInTheDocument()
      // A spoiler step is marked as one — a reviewer has to know which step
      // the learner will not see until they have answered.
      expect(screen.getByText('spoiler')).toBeInTheDocument()

      // The regression the card was added for: a question-shaped draft in the
      // same queue still renders rather than taking the panel down with it.
      expect(screen.getByText('Drafted stem about swans.')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Approve & promote/ }),
      ).toBeInTheDocument()
    })

    it('says what approving it does, and never offers the question wording', async () => {
      render(<AuthoringPanel />)
      await screen.findByText('Pending review (3)')
      // "Approve → guides", not "Approve & promote": a guide is served from a
      // different store than the bank, and the button says so.
      expect(
        screen.getByRole('button', { name: 'Approve → guides' }),
      ).toBeInTheDocument()
      expect(
        screen.getAllByRole('button', { name: /Approve & promote/ }),
      ).toHaveLength(1)
    })

    it('approves the guide by its own id and drops it from the queue', async () => {
      const approved: string[] = []
      server.use(
        http.post(
          'http://localhost:8000/api/lsat/proposals/:id/approve',
          ({ params }) => {
            approved.push(String(params.id))
            return HttpResponse.json({
              ...guideProposal,
              status: 'approved',
            })
          },
        ),
      )
      render(<AuthoringPanel />)
      await screen.findByText('Pending review (3)')

      fireEvent.click(screen.getByRole('button', { name: 'Approve → guides' }))
      await waitFor(() =>
        expect(screen.getByText('Pending review (2)')).toBeInTheDocument(),
      )
      // The guide's id reached the endpoint — not the question draft's.
      expect(approved).toEqual(['prop-g-1'])
      expect(screen.queryByText('solve guide')).not.toBeInTheDocument()
      // …and the neighbouring drafts are untouched.
      expect(screen.getByText('Drafted stem about swans.')).toBeInTheDocument()
      expect(screen.getByText('cross-check')).toBeInTheDocument()
    })

    it('rejects the guide by its own id', async () => {
      const rejected: string[] = []
      server.use(
        http.post(
          'http://localhost:8000/api/lsat/proposals/:id/reject',
          ({ params }) => {
            rejected.push(String(params.id))
            return HttpResponse.json({ ...guideProposal, status: 'rejected' })
          },
        ),
      )
      render(<AuthoringPanel />)
      await screen.findByText('Pending review (3)')
      // The guide card's own Reject, found through the card rather than by
      // position in a list of three.
      const card = screen.getByText('solve guide').closest('article')
      expect(card).not.toBeNull()
      fireEvent.click(
        within(card as HTMLElement).getByRole('button', { name: 'Reject' }),
      )
      await waitFor(() => expect(rejected).toEqual(['prop-g-1']))
      expect(screen.queryByText('solve guide')).not.toBeInTheDocument()
    })
  })

  // BL-20260702-06: the queue showed the drafts and the weakest measured
  // concepts and nothing about the machine that produced them — no coverage
  // matrix, no manifest, no gate counts.
  describe('factory status', () => {
    it('names the next batch targets, the last manifest and the gate counts', async () => {
      render(<AuthoringPanel />)
      expect(await screen.findByText('Factory status')).toBeInTheDocument()

      // The census a reviewer needs to read a deficit against.
      expect(screen.getByText('Questions in bank')).toBeInTheDocument()
      expect(screen.getByText('42')).toBeInTheDocument()
      expect(screen.getByText('11 / 60')).toBeInTheDocument()
      expect(screen.getByText('5 / 7')).toBeInTheDocument()
      expect(screen.getByText(/LG 4 · LR 30 · RC 8/)).toBeInTheDocument()

      // The targets themselves.
      expect(screen.getByText('Next batch targets')).toBeInTheDocument()
      expect(screen.getByText('weaken')).toBeInTheDocument()
      expect(screen.getByText('parallel-flaw')).toBeInTheDocument()

      expect(screen.getByText('mfst-20260905-abc123')).toBeInTheDocument()
      expect(screen.getByText(/12 jobs · bulk 8 · standard 4/)).toBeInTheDocument()
      expect(screen.getByText(/OllamaExecutor ×4/)).toBeInTheDocument()
      expect(
        screen.getByText(/2 flagged for answer balance/),
      ).toBeInTheDocument()
    })

    it('leaves the queue working when the snapshot cannot be loaded', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/factory/status', () =>
          HttpResponse.error(),
        ),
      )
      render(<AuthoringPanel />)
      // The reviewer's actual job is unaffected.
      expect(await screen.findByText('Pending review (3)')).toBeInTheDocument()
      await waitFor(() =>
        expect(screen.queryByText('Factory status')).not.toBeInTheDocument(),
      )
    })

    it('says so when no batch has ever been planned', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/factory/status', () =>
          HttpResponse.json({
            ...lsatFactoryStatusFixture,
            latest_manifest: null,
            latest_manifest_summary: null,
          }),
        ),
      )
      render(<AuthoringPanel />)
      expect(
        await screen.findByText(/No generation manifest has been written yet/),
      ).toBeInTheDocument()
    })
  })
})
