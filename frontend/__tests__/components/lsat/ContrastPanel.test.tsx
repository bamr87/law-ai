import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import ContrastPanel, { tryHref } from '@/components/lsat/ContrastPanel'
import type { LsatContrastSet } from '@/lib/api'
import { server } from '@/mocks/server'

const set: LsatContrastSet = {
  root_id: 'lr-002',
  question_id: 'lr-097',
  count: 3,
  spoilers: true,
  members: [
    {
      id: 'lr-002',
      is_root: true,
      difficulty: 'med',
      archetype_id: 'lr-weaken',
      archetype_name: 'Weaken',
      family: 'strengthen-weaken',
      task: 'Undermine the link.',
      question_sentence: 'Which one of the following, if true, most weakens the argument?',
      contrast_note: null,
    },
    {
      id: 'lr-097',
      is_root: false,
      difficulty: 'med',
      archetype_id: 'lr-strengthen',
      archetype_name: 'Strengthen',
      family: 'strengthen-weaken',
      task: 'Support the link.',
      question_sentence: 'Which one of the following, if true, most strengthens the argument?',
      contrast_note: 'Same argument as the Weaken version; the key does the reverse job.',
    },
    {
      id: 'lr-098',
      is_root: false,
      difficulty: 'med',
      archetype_id: 'lr-necessary-assumption',
      archetype_name: 'Necessary Assumption',
      family: 'assumption',
      task: 'Find what it relies on.',
      question_sentence: 'The argument depends on assuming which one of the following?',
      contrast_note: 'The modest denial of the weaken attack.',
    },
  ],
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/questions/lr-097/contrast', () =>
      HttpResponse.json(set),
    ),
    http.get('http://localhost:8000/api/lsat/questions/lr-001/contrast', () =>
      HttpResponse.json({ ...set, question_id: 'lr-001', root_id: 'lr-001', count: 1, members: [set.members[0]] }),
    ),
  )
})

describe('ContrastPanel (spec 054)', () => {
  it('shows the graded item note, the siblings with their tasks, and try links', async () => {
    render(<ContrastPanel questionId="lr-097" section="LR" />)
    expect(
      await screen.findByRole('region', { name: /same argument, different question/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/the key does the reverse job/)).toBeInTheDocument()
    expect(screen.getByText('Weaken')).toBeInTheDocument()
    expect(screen.getByText('original')).toBeInTheDocument()
    expect(screen.getByText('Necessary Assumption')).toBeInTheDocument()
    expect(screen.queryByText('Strengthen')).not.toBeInTheDocument()
    // Sibling notes are behind a disclosure, never open by default.
    expect(screen.getByText('The modest denial of the weaken attack.').closest('details')).not.toHaveAttribute('open')
    const links = screen.getAllByRole('link', { name: /try it/i })
    expect(links[0]).toHaveAttribute('href', '/lsat?tab=LR&question=lr-002')
    expect(tryHref('LR', 'lr-098')).toBe('/lsat?tab=LR&question=lr-098')
  })

  it('renders nothing for a question with no variations', async () => {
    const { container } = render(<ContrastPanel questionId="lr-001" section="LR" />)
    await new Promise((r) => setTimeout(r, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
