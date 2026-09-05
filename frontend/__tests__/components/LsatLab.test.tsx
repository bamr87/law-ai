import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import LsatLab from '@/components/LsatLab'
import {
  __resetTimerStore,
  getTimerSnapshot,
} from '@/lib/lsat/timerStore'
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
  // The timer store is module-level, so pace would leak between cases.
  __resetTimerStore()
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
    // The section timer is docked in the sidebar by default (spec 043), so the
    // page itself no longer renders it. Dock behaviour is covered by
    // __tests__/shell/lsatTimerDock.test.tsx.
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
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
    // Spec 045 FR-12: the author-rationale block with external source links
    // is gone — post-grade references resolve only to the concept catalog.
    // This supersedes the earlier assertion that the rationale text renders.
    expect(screen.queryByText(/Author rationale/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Hasty generalisation/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: /LSAC LR overview/i }),
    ).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText(/Derived from/i)).toBeInTheDocument()
    })
    expect(
      (await screen.findAllByText('flaw-in-reasoning')).length,
    ).toBeGreaterThan(1)
    // Pace now lives in the timer store, because the timer can be docked in a
    // side panel — a different React subtree from this page (spec 043).
    expect(getTimerSnapshot().answered).toBe(1)
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

  // The concept catalog is no longer a tab here — it moved into the library,
  // next to the articles that teach those concepts. Covered by
  // `__tests__/components/lsat/LsatLibrary.test.tsx`.
  it('offers no concept catalog tab, and points at the library instead', async () => {
    render(<LsatLab />)
    expect(
      screen.queryByRole('tab', { name: /^Concepts$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /knowledge library/i }),
    ).toHaveAttribute('href', '/lsat/library')
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

  it('drives a whole LR drill from the keyboard, without losing focus', async () => {
    // The keyboard contract is bound to the card element, so *where focus is*
    // after each step is the test: a keystroke that lands on <body> reaches
    // nothing, which is how a mouse-free run used to stall after one question.
    let served = 0
    server.use(
      http.get('http://localhost:8000/api/lsat/questions', () => {
        served += 1
        return HttpResponse.json({
          count: 1,
          questions: [{ ...sampleQuestion, id: `lr-00${served}` }],
        })
      }),
    )

    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))
    await waitFor(() =>
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument(),
    )
    expect(screen.getByText('lr-001')).toBeInTheDocument()

    const choice = screen.getByRole('radio', { name: /A.*Alpha/ })
    choice.focus()
    fireEvent.keyDown(choice, { key: 'b' })
    expect(screen.getByRole('radio', { name: /B.*Bravo/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    fireEvent.keyDown(choice, { key: 'Enter' })
    await waitFor(() =>
      expect(screen.getByText(/Incorrect — answer was C/)).toBeInTheDocument(),
    )
    // Graded choices stay in the focus order. `disabled` would have thrown
    // focus to <body>, outside the element every shortcut is bound to.
    expect(choice).toHaveAttribute('aria-disabled', 'true')
    expect(choice).not.toBeDisabled()
    expect(document.activeElement).toBe(choice)

    fireEvent.keyDown(choice, { key: 'n' })
    await waitFor(() => expect(screen.getByText('lr-002')).toBeInTheDocument())
    // Focus followed the new question in, so the next keystroke has somewhere
    // to land.
    expect(document.activeElement).not.toBe(document.body)
    expect(document.activeElement).toHaveTextContent('lr-002')
  })

  it('offers no practice jump for a section the lab cannot drill', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/sections', () =>
        HttpResponse.json({
          count: sampleSections.sections.length + 1,
          sections: [
            ...sampleSections.sections,
            {
              code: 'WS',
              name: 'Argumentative Writing',
              description: 'One essay, no answer key.',
              format: 'Prompt + perspectives',
              timing: '35 min',
              scoring: 'Unscored, sent to schools',
              skills: ['take a position'],
              tips: ['Name the trade-off'],
              concepts: [],
              references: [],
              question_count: 0,
            },
          ],
        }),
      ),
    )

    render(<LsatLab />)
    await waitFor(() =>
      expect(screen.getByText('Argumentative Writing')).toBeInTheDocument(),
    )
    // WS has no tab, so a "Practice WS" button selected nothing and rendered
    // an empty tabpanel — a dead end with no marked way back.
    expect(
      screen.queryByRole('button', { name: /Practice WS/i }),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/No drill in the lab yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Practice LR/i })).toBeInTheDocument()
  })
})
