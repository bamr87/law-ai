import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import PlaybookBrowser, { drillHref } from '@/components/lsat/PlaybookBrowser'
import type { LsatPlaybook } from '@/lib/api'
import { server } from '@/mocks/server'

const weaken: LsatPlaybook = {
  archetype_id: 'lr-weaken',
  name: 'Weaken',
  section: 'LR',
  family: 'strengthen-weaken',
  concepts: ['weaken', 'alternative-cause'],
  cues: ['most weakens the argument?'],
  task: 'Undermine the link.',
  strategies: [{ id: 'attack-the-link', name: 'Attack or defend the link', sections: ['LR'], summary: 's' }],
  method: ['Find the conclusion.', 'Predict the attack.'],
  traps: [{ id: 'opposite-answer', name: 'The opposite answer', summary: 'Does the reverse.' }],
  confused_with: [{ id: 'lr-strengthen', name: 'Strengthen' }],
}
const mainPoint: LsatPlaybook = {
  ...weaken,
  archetype_id: 'rc-main-point',
  name: 'Main Point',
  section: 'RC',
  family: 'global',
  concepts: ['main-point', 'rc-structure'],
  cues: ['main point of the passage?'],
  confused_with: [],
}

beforeEach(() => {
  server.use(
    http.get('http://localhost:8000/api/lsat/playbooks', () =>
      HttpResponse.json({
        playbooks: [weaken, mainPoint],
        count: 2,
        strategies: weaken.strategies,
        traps: weaken.traps,
      }),
    ),
  )
})

describe('PlaybookBrowser (spec 053 FR-8)', () => {
  it('lists one section at a time with cues, method, traps and a drill link', async () => {
    render(<PlaybookBrowser />)
    expect(await screen.findByRole('heading', { name: 'Weaken' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Main Point' })).not.toBeInTheDocument()
    expect(screen.getByText(/“most weakens the argument\?”/)).toBeInTheDocument()
    expect(screen.getByText('Find the conclusion.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /drill this type/i })).toHaveAttribute(
      'href',
      '/lsat?tab=LR&archetype=lr-weaken',
    )
    // The shared trap glossary renders once, below the catalog.
    expect(screen.getByRole('heading', { name: /trap glossary/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /reading comprehension/i }))
    expect(await screen.findByRole('heading', { name: 'Main Point' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Weaken' })).not.toBeInTheDocument()
  })

  it('links passage sections through their primary concept', () => {
    expect(drillHref(mainPoint)).toBe('/lsat?tab=RC&concept=main-point')
    expect(drillHref(weaken)).toBe('/lsat?tab=LR&archetype=lr-weaken')
  })

  it('reports a failed load', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/playbooks', () =>
        HttpResponse.json({ detail: 'down' }, { status: 500 }),
      ),
    )
    render(<PlaybookBrowser />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
