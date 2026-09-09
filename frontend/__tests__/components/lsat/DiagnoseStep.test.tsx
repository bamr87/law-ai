import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DiagnoseStep from '@/components/lsat/DiagnoseStep'
import type { LsatDiagnosisPrompt, LsatDiagnosisResult } from '@/lib/api'
import { server } from '@/mocks/server'

const prompt: LsatDiagnosisPrompt = {
  question_id: 'lr-002',
  section: 'LR',
  type_options: [
    { id: 'lr-strengthen', name: 'Strengthen' },
    { id: 'lr-weaken', name: 'Weaken' },
    { id: 'lr-causal-flaw', name: 'Causal Flaw' },
  ],
  strategy_options: [
    { id: 'attack-the-link', name: 'Attack or defend the link' },
    { id: 'negation-test', name: 'Negation test' },
  ],
}

const result: LsatDiagnosisResult = {
  question_id: 'lr-002',
  section: 'LR',
  archetype_id: 'lr-weaken',
  archetype_name: 'Weaken',
  family: 'strengthen-weaken',
  chosen_archetype: 'lr-strengthen',
  chosen_archetype_name: 'Strengthen',
  archetype_correct: false,
  family_correct: true,
  chosen_strategy: 'attack-the-link',
  strategy_correct: true,
  matched_cue: 'weakens',
  playbook: {
    archetype_id: 'lr-weaken',
    name: 'Weaken',
    section: 'LR',
    family: 'strengthen-weaken',
    concepts: ['weaken'],
    cues: ['Which one of the following, if true, most weakens the argument?'],
    task: 'Pick the new fact that makes the conclusion less likely.',
    strategies: [
      { id: 'attack-the-link', name: 'Attack or defend the link', sections: ['LR'], summary: 'Never the premises.' },
    ],
    method: ['Find the conclusion.', 'Predict the attack.'],
    traps: [{ id: 'opposite-answer', name: 'The opposite answer', summary: 'A strengthener.' }],
    confused_with: [{ id: 'lr-strengthen', name: 'Strengthen' }],
  },
}

let posted: unknown = null

beforeEach(() => {
  posted = null
  server.use(
    http.get('http://localhost:8000/api/lsat/questions/lr-002/diagnose', () =>
      HttpResponse.json(prompt),
    ),
    http.post(
      'http://localhost:8000/api/lsat/questions/lr-002/diagnose',
      async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(result)
      },
    ),
  )
})

describe('DiagnoseStep (spec 053)', () => {
  it('deals type and strategy options and gates the check on a type', async () => {
    render(<DiagnoseStep questionId="lr-002" section="LR" onComplete={() => {}} />)
    const types = await screen.findByRole('radiogroup', { name: /what type of question/i })
    expect(types).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Weaken' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: /which strategy/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /check my read/i })).toBeDisabled()
  })

  it('submits the call, shows the verdicts and the playbook, then continues', async () => {
    const onComplete = vi.fn()
    render(<DiagnoseStep questionId="lr-002" section="LR" onComplete={onComplete} />)
    fireEvent.click(await screen.findByRole('radio', { name: 'Strengthen' }))
    fireEvent.click(screen.getByRole('radio', { name: /attack or defend/i }))
    fireEvent.click(screen.getByRole('button', { name: /check my read/i }))

    expect(await screen.findByText(/Type: close/)).toBeInTheDocument()
    expect(posted).toEqual({ archetype_id: 'lr-strengthen', strategy_id: 'attack-the-link' })
    expect(screen.getByText(/Strategy: right/)).toBeInTheDocument()
    expect(screen.getByText(/specifically Weaken, not Strengthen/)).toBeInTheDocument()
    // The cue that gave it away, the method and the traps are the feedback.
    expect(screen.getByText(/“weakens”/)).toBeInTheDocument()
    expect(screen.getByText('Find the conclusion.')).toBeInTheDocument()
    expect(screen.getByText('The opposite answer')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open the weaken playbook/i })).toHaveAttribute(
      'href',
      '/lsat/playbooks#lr-weaken',
    )

    fireEvent.click(screen.getByRole('button', { name: /now answer it/i }))
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ archetype_id: 'lr-weaken' }))
  })

  it('can be skipped, handing back null', async () => {
    const onComplete = vi.fn()
    render(<DiagnoseStep questionId="lr-002" section="LR" onComplete={onComplete} />)
    fireEvent.click(await screen.findByRole('button', { name: /skip and show the choices/i }))
    expect(onComplete).toHaveBeenCalledWith(null)
  })

  it('offers the choices when the prompt cannot load', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/questions/lr-002/diagnose', () =>
        HttpResponse.json({ detail: 'no type' }, { status: 404 }),
      ),
    )
    const onComplete = vi.fn()
    render(<DiagnoseStep questionId="lr-002" section="LR" onComplete={onComplete} />)
    fireEvent.click(await screen.findByRole('button', { name: /show the choices instead/i }))
    expect(onComplete).toHaveBeenCalledWith(null)
  })
})
