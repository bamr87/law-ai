import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OverviewPanel from '@/components/lsat/OverviewPanel'
import { server } from '@/mocks/server'

const section = (code: string, name: string, question_count: number) => ({
  code,
  name,
  description: `${name} in one line.`,
  format: 'Prompt + choices',
  timing: '~35 min',
  scoring: 'Each item 1 pt',
  skills: [],
  tips: ['Read the stem first'],
  concepts: [],
  references: [{ title: `${code} overview`, url: `https://example.test/${code}` }],
  question_count,
})

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/sections', () =>
      HttpResponse.json({
        count: 2,
        sections: [
          section('LR', 'Logical Reasoning', 7),
          section('WS', 'Argumentative Writing', 0),
        ],
      }),
    ),
  )
})

describe('OverviewPanel', () => {
  it('renders a card per section with its bank size and a practice jump', async () => {
    const onJump = vi.fn()
    render(<OverviewPanel onJump={onJump} />)
    expect(await screen.findByText('Logical Reasoning')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'LR overview' })).toHaveAttribute(
      'href',
      'https://example.test/LR',
    )
    fireEvent.click(screen.getByRole('button', { name: /Practice LR/ }))
    expect(onJump).toHaveBeenCalledWith('LR')
  })

  // BL-20260901-09: WS was the one section whose card dead-ended in "No drill
  // in the lab yet" and sent the learner to the published static site. It has a
  // panel now, so it jumps like the others — and its census is prompts, not
  // keyed items, so the card no longer reports a bank size of zero.
  it('jumps into the writing surface and counts prompts, not items', async () => {
    const onJump = vi.fn()
    render(<OverviewPanel onJump={onJump} />)
    expect(await screen.findByText('Argumentative Writing')).toBeInTheDocument()
    expect(screen.queryByText(/No drill in the lab yet/)).not.toBeInTheDocument()
    expect(screen.getByText('Prompts in bank')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Practice WS/ }))
    expect(onJump).toHaveBeenCalledWith('WS')
  })

  it('links to the knowledge library', () => {
    render(<OverviewPanel onJump={() => {}} />)
    expect(screen.getByRole('link', { name: /knowledge library/i })).toHaveAttribute(
      'href',
      '/lsat/library',
    )
  })
})
