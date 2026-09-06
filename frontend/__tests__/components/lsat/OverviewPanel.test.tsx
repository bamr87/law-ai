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

  it('offers no jump for a section the lab cannot drill', async () => {
    render(<OverviewPanel onJump={() => {}} />)
    expect(await screen.findByText('Argumentative Writing')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Practice WS/ })).not.toBeInTheDocument()
    expect(screen.getByText(/No drill in the lab yet/)).toBeInTheDocument()
  })

  it('links to the knowledge library', () => {
    render(<OverviewPanel onJump={() => {}} />)
    expect(screen.getByRole('link', { name: /knowledge library/i })).toHaveAttribute(
      'href',
      '/lsat/library',
    )
  })
})
