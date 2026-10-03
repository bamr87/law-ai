import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

// BL-20260831-28: the factory drafts writing prompts into the same queue.
// A WS draft carries no `choices`, so before it had a card of its own it fell
// through to the question card and threw inside `choices.map`.
const writingProposal = {
  ...questionProposal,
  id: 'prop-w-1',
  proposal_kind: 'writing_prompt',
  section: 'WS',
  draft: {
    id: 'ws-004',
    title: 'Ferry or bridge',
    rubric_id: 'ws-argumentative-v1',
    difficulty: 'med',
    issue: 'Should the county fund the ferry or the bridge?',
    context: 'The county has one grant and two shovel-ready projects.',
    task: 'Argue for one position and answer the other.',
    positions: [
      { id: 'fund-ferry', name: 'Fund the ferry', summary: 'Serves the isles.' },
      { id: 'fund-bridge', name: 'Fund the bridge', summary: 'Serves commuters.' },
    ],
    perspectives: [
      { id: 'p1', text: 'The harbourmaster notes ferry ridership is seasonal.' },
      { id: 'p2', text: 'A planner notes the bridge locks in car traffic.' },
      { id: 'p3', text: 'An islander has no other winter route.' },
    ],
    concepts: ['thesis-position'],
  },
}

// BL-20260702-02 / BL-20260702-07: what the factory recorded about a draft —
// the judge's objection and a passage the job parked — beside the draft.
const judgedProposal = {
  ...questionProposal,
  id: 'prop-q-2',
  draft: { ...questionProposal.draft, stem: 'Judged stem about ferries.' },
  meta: {
    factory: {
      manifest_id: 'mfst-1',
      job_id: 'mfst-1-job01',
      tier: 'bulk',
      executor: 'OllamaExecutor',
      pending_passage_path: '/app/var/lsat_factory/drafts/pending_passages/mfst-1-job01.passage.json',
      judge: {
        verdict: 'fail',
        single_best_answer: false,
        solved_key: 'D',
        key_agrees: false,
        ambiguity: 0.8,
        issues: ['C and D are both defensible under the stem.'],
        confidence: 0.6,
        rationale: 'The stem does not exclude D.',
        model: 'ollama/llama3',
        degraded: false,
      },
    },
  },
}

// A guide the factory drafted beside a question that is still pending: it
// names the *proposal*, because the question has no bank id yet.
const pairedGuideProposal = {
  ...guideProposal,
  id: 'prop-g-2',
  draft: { ...guideProposal.draft, question_id: 'prop-q-2' },
  meta: { guide_for_proposal: 'prop-q-2' },
}

const flaggedProposal = {
  ...questionProposal,
  id: 'prop-q-flagged',
  draft: { ...questionProposal.draft, stem: 'Flagged stem about swans.' },
  meta: {
    review: {
      clarity: 0.4,
      ambiguity: 0.3,
      single_best_answer: 0.4,
      overall: 0.37,
      flags: ['two defensible choices'],
      rationale: 'C is arguable.',
      flagged: true,
      model: 'ollama/llama3',
      degraded: false,
    },
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

  // BL-20260831-28: a writing draft must survive the queue it is now filed in.
  describe('writing-prompt drafts', () => {
    beforeEach(() => {
      server.use(
        http.get('http://localhost:8000/api/lsat/proposals', () =>
          HttpResponse.json({
            proposals: [writingProposal, questionProposal],
            count: 2,
            status: 'pending',
          }),
        ),
        http.post(
          'http://localhost:8000/api/lsat/proposals/:id/approve',
          ({ params }) =>
            HttpResponse.json({
              ...writingProposal,
              id: params.id,
              status: 'approved',
              writing_prompt_id: 'ws-004',
            }),
        ),
      )
    })

    it('renders a writing draft on its own card without breaking the queue', async () => {
      render(<AuthoringPanel />)
      expect(await screen.findByText('Pending review (2)')).toBeInTheDocument()
      const card = screen.getByTestId('writing-proposal-card')
      expect(within(card).getByText('writing prompt')).toBeInTheDocument()
      expect(within(card).getByText('Ferry or bridge')).toBeInTheDocument()
      expect(
        within(card).getByText('Should the county fund the ferry or the bridge?'),
      ).toBeInTheDocument()
      // And the question draft next to it still renders — the crash used to
      // take the whole list down, not just the writing row.
      expect(screen.getByText('Drafted stem about swans.')).toBeInTheDocument()
    })

    it('offers an approve button that names the writing library', async () => {
      render(<AuthoringPanel />)
      await screen.findByText('Pending review (2)')
      const approve = screen.getByRole('button', {
        name: /Approve → writing library/,
      })
      fireEvent.click(approve)
      await waitFor(() =>
        expect(screen.getByText('Pending review (1)')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('writing-proposal-card')).not.toBeInTheDocument()
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

  // BL-20260905-45: the judge tier wrote an objection into the proposal and
  // the queue rendered none of it, so the reviewer re-derived it by hand.
  describe('factory judge verdict', () => {
    beforeEach(() => {
      server.use(
        http.get('http://localhost:8000/api/lsat/proposals', () =>
          HttpResponse.json({
            proposals: [judgedProposal, pairedGuideProposal],
            count: 2,
            status: 'pending',
          }),
        ),
      )
    })

    it('shows the verdict, the disputed key and the objection', async () => {
      render(<AuthoringPanel />)
      await screen.findByText('Judged stem about ferries.')
      const card = screen.getByText('Judged stem about ferries.').closest('article')
      expect(card).not.toBeNull()
      const judged = within(card as HTMLElement)
      expect(judged.getByText('Judge')).toBeInTheDocument()
      expect(judged.getByText('fail')).toBeInTheDocument()
      expect(judged.getByText(/key disputed · solved D/)).toBeInTheDocument()
      expect(judged.getByText('second defensible choice')).toBeInTheDocument()
      expect(
        judged.getByText('C and D are both defensible under the stem.'),
      ).toBeInTheDocument()
    })

    it('never reads a degraded verdict as approval', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/proposals', () =>
          HttpResponse.json({
            proposals: [
              {
                ...judgedProposal,
                meta: {
                  factory: {
                    judge: {
                      ...judgedProposal.meta.factory.judge,
                      verdict: 'pass',
                      degraded: true,
                    },
                  },
                },
              },
            ],
            count: 1,
            status: 'pending',
          }),
        ),
      )
      render(<AuthoringPanel />)
      expect(
        await screen.findByText(/not reviewed — no provider answered/),
      ).toBeInTheDocument()
      expect(screen.queryByText('pass')).not.toBeInTheDocument()
    })

    it('names the guide drafted alongside a pending question, from both sides', async () => {
      render(<AuthoringPanel />)
      await screen.findByText('Judged stem about ferries.')

      const question = screen
        .getByText('Judged stem about ferries.')
        .closest('article') as HTMLElement
      expect(
        within(question).getByText(/1 solve guide drafted with this item/),
      ).toBeInTheDocument()
      expect(within(question).getByText('prop-g-2')).toBeInTheDocument()

      const guide = screen.getByText('solve guide').closest('article') as HTMLElement
      // The guide names the question it was drafted with, by proposal id —
      // the id the question card is titled with, not a bank id it has none of.
      expect(
        within(guide).getByText(/Drafted with pending question/).textContent,
      ).toContain('prop-q-2')
    })
  })

  // BL-20260905-56: the passage endpoint existed and only curl could reach it.
  describe('parked passage promotion', () => {
    beforeEach(() => {
      server.use(
        http.get('http://localhost:8000/api/lsat/proposals', () =>
          HttpResponse.json({
            proposals: [judgedProposal],
            count: 1,
            status: 'pending',
          }),
        ),
      )
    })

    it('promotes the parked passage by its path and reloads the queue', async () => {
      const posted: unknown[] = []
      server.use(
        http.post(
          'http://localhost:8000/api/lsat/proposals/passages/approve',
          async ({ request }) => {
            posted.push(await request.json())
            return HttpResponse.json({
              passage_id: 'rc-p-009',
              section: 'RC',
              title: 'Ferries',
              pending_passage_path: judgedProposal.meta.factory.pending_passage_path,
              linked_proposals: ['prop-q-2'],
              promoted_at: '2026-09-05T00:00:00Z',
            })
          },
        ),
      )
      render(<AuthoringPanel />)
      fireEvent.click(
        await screen.findByRole('button', { name: 'Promote passage' }),
      )
      await waitFor(() => expect(posted).toHaveLength(1))
      expect(posted[0]).toMatchObject({
        pending_passage_path:
          judgedProposal.meta.factory.pending_passage_path,
      })
    })

    it('offers no promote button once the draft carries a real passage', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/proposals', () =>
          HttpResponse.json({
            proposals: [
              {
                ...judgedProposal,
                draft: { ...judgedProposal.draft, passage_id: 'rc-p-009' },
              },
            ],
            count: 1,
            status: 'pending',
          }),
        ),
      )
      render(<AuthoringPanel />)
      await screen.findByText('Judged stem about ferries.')
      expect(
        screen.queryByRole('button', { name: 'Promote passage' }),
      ).not.toBeInTheDocument()
    })
  })

  // BL-20260905-83: a reviewer with fifty rows should not scroll to find the
  // five the blind pre-review doubted.
  it('sorts pre-flagged drafts to the top of the queue', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/proposals', () =>
        HttpResponse.json({
          proposals: [questionProposal, guideProposal, flaggedProposal],
          count: 3,
          status: 'pending',
        }),
      ),
    )
    render(<AuthoringPanel />)
    await screen.findByText('Pending review (3)')
    const stems = screen
      .getAllByRole('article')
      .map((card) => card.textContent ?? '')
    expect(stems[0]).toContain('Flagged stem about swans.')
    // …and the unflagged rows keep the order the API returned them in.
    expect(stems[1]).toContain('Drafted stem about swans.')
    expect(stems[2]).toContain('solve guide')
  })


})

describe('spec 054: type checks and contrast variations in the queue', () => {
  it('renders a type-check card with restamp / keep actions', async () => {
    const { ProposalCard } = await import('@/components/lsat/AuthoringPanel')
    const onApprove = vi.fn()
    const onReject = vi.fn()
    render(
      <ProposalCard
        proposal={{
          id: 'prop-tc1',
          status: 'pending',
          created_at: '2026-09-08T00:00:00Z',
          updated_at: '2026-09-08T00:00:00Z',
          proposal_kind: 'typecheck',
          section: 'LR',
          difficulty: 'med',
          agent_trace_id: '',
          model: 'claude_code/x',
          confidence: 0.7,
          source_concept_ids: [],
          draft: {
            question_id: 'lr-002',
            section: 'LR',
            stem: 'City planner: ...',
            stamped_archetype: 'lr-weaken',
            cue_archetype: 'lr-weaken',
            model_archetype: 'lr-causal-flaw',
            rationale: 'It says flawed because.',
            confidence: 0.7,
            model: 'claude_code/x',
          },
        }}
        busy={false}
        onApprove={onApprove}
        onReject={onReject}
        onPromotePassage={() => {}}
      />,
    )
    expect(screen.getByTestId('typecheck-proposal-card')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /restamp as lr-causal-flaw/i }))
    expect(onApprove).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /keep current stamp/i }))
    expect(onReject).toHaveBeenCalled()
  })

  it('shows lineage and the revision history on a variation draft', async () => {
    const { ProposalCard } = await import('@/components/lsat/AuthoringPanel')
    render(
      <ProposalCard
        proposal={{
          id: 'prop-v1',
          status: 'pending',
          created_at: '2026-09-08T00:00:00Z',
          updated_at: '2026-09-08T00:00:00Z',
          proposal_kind: 'question',
          section: 'LR',
          difficulty: 'med',
          agent_trace_id: '',
          model: 'claude_code/x',
          confidence: 0.8,
          source_concept_ids: ['strengthen'],
          draft: {
            section: 'LR',
            difficulty: 'med',
            stem: 'Stimulus.\n\nWhich one of the following most strengthens?',
            choices: ['A', 'B', 'C', 'D', 'E'].map((label) => ({ label: label as 'A', text: `c${label}` })),
            correct: 'A',
            explanation: 'Because.',
            concepts: ['strengthen'],
            confidence: 0.8,
          },
          meta: {
            variation_of: 'lr-002',
            factory: { archetype_id: 'lr-strengthen' },
            revisions: {
              accepted: false,
              rounds: [
                { round: 1, model: 'm', gate_issues: ['the stem reads as lr-weaken'], critique: ['x'], accepted: false },
                { round: 2, model: 'm', gate_issues: [], judge: { verdict: 'fail', single_best_answer: false, solved_key: 'B', key_agrees: false, ambiguity: 0.5, issues: ['(B) also works'], confidence: 0.8, rationale: '', model: 'm', degraded: false }, critique: [], accepted: false },
              ],
            },
          },
        }}
        busy={false}
        onApprove={() => {}}
        onReject={() => {}}
        onPromotePassage={() => {}}
      />,
    )
    expect(screen.getByText(/variation of lr-002 → lr-strengthen/)).toBeInTheDocument()
    const history = screen.getByTestId('revision-history')
    expect(history).toHaveTextContent('2 drafting rounds')
    expect(history).toHaveTextContent('NOT accepted')
    expect(history).toHaveTextContent('gate: the stem reads as lr-weaken')
    expect(history).toHaveTextContent('judge: fail (blind key disagrees)')
  })
})

describe('spec 054: rewrites and the final review', () => {
  it('renders a rewrite card with the original verdict, the change summary and replace/keep actions', async () => {
    const { ProposalCard } = await import('@/components/lsat/AuthoringPanel')
    const onApprove = vi.fn()
    const onReject = vi.fn()
    render(
      <ProposalCard
        proposal={{
          id: 'prop-rw1',
          status: 'pending',
          created_at: '2026-09-08T00:00:00Z',
          updated_at: '2026-09-08T00:00:00Z',
          proposal_kind: 'rewrite',
          section: 'LR',
          difficulty: 'med',
          agent_trace_id: '',
          model: 'claude_code/x',
          confidence: 0.8,
          source_concept_ids: ['weaken'],
          draft: {
            question_id: 'lr-002',
            section: 'LR',
            difficulty: 'med',
            stem: 'Stimulus.\n\nWhich weakens?',
            choices: ['A', 'B', 'C', 'D', 'E'].map((label) => ({ label: label as 'A', text: `c${label}` })),
            correct: 'D',
            explanation: 'Because.',
            concepts: ['weaken'],
            confidence: 0.8,
            change_summary: 'Tightened choice A so it no longer presupposes a cost estimate.',
          },
          meta: {
            rewrite_of: 'lr-002',
            original_judge: { verdict: 'flag', single_best_answer: true, solved_key: 'D', key_agrees: true, ambiguity: 0.2, issues: ['Choice A presupposes a cost estimate.'], confidence: 0.8, rationale: '', model: 'm', degraded: false },
            final_review: { role: 'final_review', verdict: 'pass', single_best_answer: true, solved_key: 'D', key_agrees: true, ambiguity: 0, issues: [], confidence: 0.9, rationale: '', model: 'claude_code/claude-fable-5-1', degraded: false },
            revisions: { accepted: true, rounds: [{ round: 1, model: 'm', gate_issues: [], critique: [], accepted: true }] },
          },
        }}
        busy={false}
        onApprove={onApprove}
        onReject={onReject}
        onPromotePassage={() => {}}
      />,
    )
    expect(screen.getByTestId('rewrite-proposal-card')).toBeInTheDocument()
    expect(screen.getByText(/Tightened choice A/)).toBeInTheDocument()
    expect(screen.getByText('Choice A presupposes a cost estimate.')).toBeInTheDocument()
    expect(screen.getByTestId('final-review-badge')).toHaveTextContent('final review: pass')
    fireEvent.click(screen.getByRole('button', { name: /approve → replace lr-002/i }))
    expect(onApprove).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /keep original/i }))
    expect(onReject).toHaveBeenCalled()
  })
})
