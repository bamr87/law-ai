import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import LsatLab from '@/components/LsatLab'
import { server } from '@/mocks/server'

const sampleSections = {
  count: 3,
  sections: [
    {
      code: 'LR',
      name: 'Logical Reasoning',
      description: 'Short arguments with question stems.',
      format: 'Short prompt + 5 choices',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['identify conclusions'],
      tips: ['Diagram conditionals'],
      concepts: ['modus-tollens'],
      references: [{ title: 'LSAC LR overview', url: 'https://example.test/lr' }],
      question_count: 7,
    },
    {
      code: 'RC',
      name: 'Reading Comprehension',
      description: 'Long passages with linked questions.',
      format: 'Passage + 5–8 questions',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['main point'],
      tips: ['Summarise each paragraph'],
      concepts: ['main-point'],
      references: [],
      question_count: 3,
    },
    {
      code: 'LG',
      name: 'Analytical Reasoning',
      description: 'Sequencing and grouping puzzles.',
      format: 'Setup + rules + 5–7 questions',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['symbolize rules'],
      tips: ['Sketch every fixed slot'],
      concepts: ['sequencing'],
      references: [],
      question_count: 3,
    },
  ],
}

const sampleQuestion = {
  id: 'lr-001',
  section: 'LR',
  type: 'LR',
  difficulty: 'med',
  stem: 'All swans observed are white. Therefore all swans are white.',
  choices: [
    { label: 'A', text: 'Alpha' },
    { label: 'B', text: 'Bravo' },
    { label: 'C', text: 'Charlie' },
    { label: 'D', text: 'Delta' },
    { label: 'E', text: 'Echo' },
  ],
  concepts: ['flaw-in-reasoning'],
  references: [],
  passage_id: null,
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/stats', () =>
      HttpResponse.json({
        attempts: 0,
        correct: 0,
        accuracy: 0,
        by_section: {},
      }),
    ),
    http.get('http://localhost:8000/api/lsat/sections', () =>
      HttpResponse.json(sampleSections),
    ),
    http.get('http://localhost:8000/api/lsat/questions', () =>
      HttpResponse.json({ count: 1, questions: [sampleQuestion] }),
    ),
    http.post('http://localhost:8000/api/lsat/grade', () =>
      HttpResponse.json({
        question_id: 'lr-001',
        correct: false,
        correct_choice: 'C',
        explanation: 'Hasty generalisation — sample bias.',
        section: 'LR',
        concepts: ['flaw-in-reasoning'],
      }),
    ),
    http.post('http://localhost:8000/api/lsat/tutor', () =>
      HttpResponse.json({
        question_id: 'lr-001',
        user_choice: 'A',
        correct_choice: 'C',
        is_correct: false,
        explanation: 'Hasty generalisation.',
        coaching: 'Walkthrough — the inductive leap is the flaw.',
        next_steps: ['Review sampling bias', 'Drill 5 more flaw items'],
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
        model: 'mistral:7b-instruct-q4_K_M',
        used_llm: true,
        confidence: 0.85,
        requires_human_review: false,
        latency_ms: 120,
      }),
    ),
    http.get('http://localhost:8000/api/lsat/concepts', () =>
      HttpResponse.json({
        count: 1,
        concepts: [
          {
            id: 'modus-tollens',
            name: 'Modus tollens',
            sections: ['LR'],
            summary: 'Deny the consequent to deny the antecedent.',
            detail: 'Deeper detail about modus tollens.',
            examples: ['If P then Q. Not Q. Therefore not P.'],
            see_also: ['contrapositive'],
            references: [
              { title: 'SEP — Logic', url: 'https://plato.stanford.edu/' },
            ],
          },
        ],
      }),
    ),
    http.get('http://localhost:8000/api/lsat/passages', () =>
      HttpResponse.json({
        count: 1,
        passages: [
          {
            id: 'rc-passage-001',
            section: 'RC',
            title: 'Federal pleading evolution',
            summary: 'Conley → Twombly → Iqbal.',
            passage: 'Long passage text.',
            setup: null,
            rules: [],
            source: 'Test',
          },
        ],
      }),
    ),
    http.get('http://localhost:8000/api/lsat/passages/rc-passage-001', () =>
      HttpResponse.json({
        count: 1,
        passage: {
          id: 'rc-passage-001',
          section: 'RC',
          title: 'Federal pleading evolution',
          summary: 'Conley → Twombly → Iqbal.',
          passage: 'Long passage text.',
          setup: null,
          rules: [],
          source: 'Test',
        },
        questions: [{ ...sampleQuestion, id: 'rc-001', section: 'RC', type: 'RC' }],
      }),
    ),
  )
})

describe('LsatLab', () => {
  it('renders the section overview by default', async () => {
    render(<LsatLab />)
    await waitFor(() => {
      expect(screen.getAllByText('Logical Reasoning').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/four-section roadmap/i)).toBeInTheDocument()
    expect(screen.getAllByText('Reading Comprehension').length).toBeGreaterThan(0)
    expect(screen.getByText('Analytical Reasoning')).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
  })

  it('switches to LR practice and grades a question', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))

    await waitFor(() => {
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument()
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )

    fireEvent.click(screen.getByRole('radio', { name: /A.*Alpha/ }))
    fireEvent.click(screen.getByRole('button', { name: /Submit/ }))

    await waitFor(() => {
      expect(
        screen.getByText(/Incorrect — answer was C/),
      ).toBeInTheDocument()
    })
    expect(screen.getByText(/Hasty generalisation/)).toBeInTheDocument()
    expect(screen.getByLabelText(/average time per question/i)).toHaveTextContent(
      /avg 0:00 \/ q/,
    )
  })

  it('invokes the AI tutor when requested', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))

    await waitFor(() =>
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('radio', { name: /A.*Alpha/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Submit$/ }))

    await waitFor(() =>
      expect(
        screen.getByText(/Incorrect — answer was C/),
      ).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /Ask AI Tutor/ }))

    await waitFor(() =>
      expect(screen.getByText(/Walkthrough — the inductive leap/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/Review sampling bias/)).toBeInTheDocument()
  })

  it('lists concepts in the catalog', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /^Concepts$/ }))
    await waitFor(() =>
      expect(screen.getByText('Modus tollens')).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByText('Modus tollens'))
    expect(
      screen.getByText(/Deeper detail about modus tollens/),
    ).toBeInTheDocument()
  })

  it('renders RC passage + questions side by side', async () => {
    render(<LsatLab />)
    fireEvent.click(
      screen.getByRole('tab', { name: /Reading Comprehension/i }),
    )
    await waitFor(() =>
      expect(screen.getByText('Federal pleading evolution')).toBeInTheDocument(),
    )
    // Passage detail loads via a second fetch after the list resolves —
    // wait for the body text instead of asserting synchronously.
    await waitFor(() =>
      expect(screen.getByText(/Long passage text/)).toBeInTheDocument(),
    )
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )
  })
})
