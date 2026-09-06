import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

const question2 = {
  ...question,
  id: 'rc-002',
  stem: 'The author would most likely agree that…',
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

/** Serve the passage with both questions, plus a grader that marks A right. */
function twoQuestionSet() {
  server.use(
    http.get('http://localhost:8000/api/lsat/passages/rc-passage-001', () =>
      HttpResponse.json({
        count: 2,
        passage,
        questions: [question, question2],
      }),
    ),
    http.post('http://localhost:8000/api/lsat/grade', async ({ request }) => {
      const body = (await request.json()) as { question_id: string }
      return HttpResponse.json({
        question_id: body.question_id,
        correct: true,
        correct_choice: 'A',
        explanation: 'Because.',
        section: 'RC',
        concepts: [],
      })
    }),
  )
}

describe('PassagePanel', () => {
  it('loads the passage list, then the active passage with its questions', async () => {
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    expect(await screen.findByText(/Long passage text/)).toBeInTheDocument()
    expect(screen.getByLabelText('Passage')).toHaveValue('rc-passage-001')
    expect(screen.getByText(/main point of the passage/)).toBeInTheDocument()
    expect(screen.getByText(/Section: Reading Comprehension/)).toBeInTheDocument()
  })

  // BL-20260606-01: RC and LG are served from the passage endpoint, so the
  // shuffle has to be asked for here too — LR asking on its own left the
  // majority of the bank with the key in the same place on every attempt.
  it('asks the passage endpoint to shuffle each question', async () => {
    const urls: string[] = []
    server.use(
      http.get(
        'http://localhost:8000/api/lsat/passages/rc-passage-001',
        ({ request }) => {
          urls.push(request.url)
          return HttpResponse.json({ count: 1, passage, questions: [question] })
        },
      ),
    )
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    await screen.findByText(/Long passage text/)
    expect(urls).not.toHaveLength(0)
    expect(urls.every((u) => new URL(u).searchParams.get('shuffle') === '1')).toBe(
      true,
    )
  })

  it('grades a shuffled passage question with the token it was served', async () => {
    const graded: { remap?: string }[] = []
    server.use(
      http.get('http://localhost:8000/api/lsat/passages/rc-passage-001', () =>
        HttpResponse.json({
          count: 1,
          passage,
          questions: [{ ...question, remap: '10.sig' }],
        }),
      ),
      http.post('http://localhost:8000/api/lsat/grade', async ({ request }) => {
        const body = (await request.json()) as { remap?: string }
        graded.push(body)
        return HttpResponse.json({
          question_id: question.id,
          correct: true,
          correct_choice: 'A',
          explanation: 'Because.',
          section: 'RC',
          concepts: [],
        })
      }),
    )
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    await screen.findByText(/main point of the passage/)
    fireEvent.click(screen.getByRole('radio', { name: /A.*Alpha/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Submit$/ }))
    expect(
      await screen.findByText('Correct', {}, { timeout: 5000 }),
    ).toBeInTheDocument()
    expect(graded[0].remap).toBe('10.sig')
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

// BL-20260901-08: RC/LG used to stack every question in one column, so there
// was nothing for N/P to mean and Tab was the only route between them.
describe('PassagePanel one-question-at-a-time drill', () => {
  function card() {
    return screen.getByRole('radiogroup', { name: /answer choices/i })
  }

  it('shows one question at a time with a numbered jump strip', async () => {
    twoQuestionSet()
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    expect(await screen.findByText(/main point of the passage/)).toBeInTheDocument()
    expect(screen.queryByText(/would most likely agree/)).not.toBeInTheDocument()
    expect(
      screen.getByRole('group', { name: 'Questions in this set' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Question 1 / 2')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Question 2, unanswered/ }),
    ).toBeInTheDocument()
  })

  it('advances on N and steps back on P', async () => {
    twoQuestionSet()
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    await screen.findByText(/main point of the passage/)

    fireEvent.keyDown(card(), { key: 'n' })
    expect(await screen.findByText(/would most likely agree/)).toBeInTheDocument()
    expect(screen.queryByText(/main point of the passage/)).not.toBeInTheDocument()
    expect(screen.getByText('Question 2 / 2')).toBeInTheDocument()

    fireEvent.keyDown(card(), { key: 'p' })
    expect(await screen.findByText(/main point of the passage/)).toBeInTheDocument()
    expect(screen.getByText('Question 1 / 2')).toBeInTheDocument()
  })

  it('keeps a graded answer when you leave the question and come back', async () => {
    const onAttempt = vi.fn()
    twoQuestionSet()
    render(<PassagePanel section="RC" onAttempt={onAttempt} />)
    await screen.findByText(/main point of the passage/)

    fireEvent.click(screen.getByRole('radio', { name: /A.*Alpha/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Submit$/ }))
    expect(await screen.findByText('Correct', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(onAttempt).toHaveBeenCalledTimes(1)
    // The strip records the outcome without re-reading the card.
    expect(
      screen.getByRole('button', { name: /Question 1, answered correctly/ }),
    ).toBeInTheDocument()

    fireEvent.keyDown(card(), { key: 'n' })
    expect(await screen.findByText(/would most likely agree/)).toBeInTheDocument()
    fireEvent.keyDown(card(), { key: 'p' })
    expect(await screen.findByText(/main point of the passage/)).toBeInTheDocument()
    // Both the grade and the pick survived the round trip.
    expect(screen.getByText('Correct')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /A.*Alpha/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    // …and it is still one attempt, not two.
    expect(onAttempt).toHaveBeenCalledTimes(1)
  })

  it('jumps straight to a question from the strip', async () => {
    twoQuestionSet()
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    await screen.findByText(/main point of the passage/)
    fireEvent.click(screen.getByRole('button', { name: /Question 2, unanswered/ }))
    expect(await screen.findByText(/would most likely agree/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Question 2, unanswered/ }),
    ).toHaveAttribute('aria-current', 'true')
  })

  it('leaves a single-question set without a strip', async () => {
    render(<PassagePanel section="RC" onAttempt={() => {}} />)
    await screen.findByText(/main point of the passage/)
    expect(
      screen.queryByRole('group', { name: 'Questions in this set' }),
    ).not.toBeInTheDocument()
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
