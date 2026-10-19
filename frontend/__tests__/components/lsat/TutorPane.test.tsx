import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import TutorPane from '@/components/lsat/TutorPane'
import { server } from '@/mocks/server'

const base = {
  question_id: 'lr-001',
  user_choice: 'A',
  correct_choice: 'C',
  is_correct: false,
  explanation: 'Hasty generalisation.',
  coaching: 'Walkthrough — the inductive leap is the flaw.',
  next_steps: ['Review sampling bias'],
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
  confidence: 0.85,
  requires_human_review: false,
  latency_ms: 120,
}

describe('TutorPane', () => {
  it('asks on open and names the model that answered', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...base,
          model: 'mistral:7b-instruct-q4_K_M',
          used_llm: true,
          cached: false,
        })
      }),
    )
    render(
      <TutorPane
        questionId="lr-001"
        userChoice="A"
        initialQuestion="Walk me through it."
      />,
    )
    expect(
      await screen.findByText(/Walkthrough — the inductive leap/),
    ).toBeInTheDocument()
    expect(body).toMatchObject({
      question_id: 'lr-001',
      user_choice: 'A',
      user_question: 'Walk me through it.',
    })
    expect(screen.getByText(/mistral:7b-instruct-q4_K_M/)).toBeInTheDocument()
    expect(screen.getByText('Flaw in reasoning')).toBeInTheDocument()
    expect(screen.queryByText(/offline fallback/)).not.toBeInTheDocument()
  })

  it('renders the default mock reply with no per-suite handler (BL-20260905-35)', async () => {
    // No `server.use` here on purpose: mocks/server.ts ships a default
    // POST /api/lsat/tutor so every suite that merely reaches the tutor gets a
    // stable, model-answered reply instead of an unhandled-request error.
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    expect(
      await screen.findByText(/Start with the conclusion/),
    ).toBeInTheDocument()
    expect(screen.getByText(/claude_code\/claude-opus-5/)).toBeInTheDocument()
    expect(screen.queryByText(/offline fallback/)).not.toBeInTheDocument()
  })

  it('sends the shuffle token so the coaching is about the board on screen', async () => {
    // BL-20260905-61: without it the tutor reasons in stored labels and can
    // name a letter the learner is not looking at.
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(base)
      }),
    )
    render(
      <TutorPane questionId="lr-001" userChoice="A" remap="41302.abcdef0123456789" />,
    )
    await screen.findByText(/Walkthrough — the inductive leap/)
    expect(body).toMatchObject({ remap: '41302.abcdef0123456789' })
  })

  it('omits the token entirely for an unshuffled serve', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(base)
      }),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    await screen.findByText(/Walkthrough — the inductive leap/)
    expect(body).not.toHaveProperty('remap')
  })

  it('labels a fallback answer as offline instead of naming a model', async () => {
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', () =>
        HttpResponse.json({
          ...base,
          model: 'fallback/offline',
          used_llm: false,
          cached: false,
          confidence: 0.55,
        }),
      ),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    expect(await screen.findByText(/offline fallback/)).toBeInTheDocument()
    expect(screen.getByText(/55% conf/)).toBeInTheDocument()
    expect(screen.queryByText(/fallback\/offline/)).not.toBeInTheDocument()
  })

  it('offers Regenerate only for a saved walkthrough (spec 045 FR-13)', async () => {
    let refreshed: unknown = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        const b = (await request.json()) as { refresh?: boolean }
        refreshed = b.refresh
        return HttpResponse.json({
          ...base,
          model: 'claude',
          used_llm: true,
          cached: true,
        })
      }),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    expect(await screen.findByText(/saved walkthrough/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Regenerate/ }))
    await screen.findByText(/saved walkthrough/)
    expect(refreshed).toBe(true)
  })
})

// --- BL-20260503-03: coaching rendered as the model writes it ---

describe('TutorPane token streaming', () => {
  it('does not ask for a stream where there is no WebSocket', async () => {
    // jsdom has none, which is the fallback path: the request goes out
    // unstreamed and the learner still gets the full walkthrough.
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...base, model: 'offline', used_llm: false })
      }),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)

    await screen.findByText(/inductive leap/)
    expect(body).not.toBeNull()
    expect(body!.stream_tokens).toBeUndefined()
    expect(body!.stream_id).toBeUndefined()
  })

  it('renders deltas while the request is still in flight', async () => {
    class ReadySocket {
      static last: ReadySocket | null = null
      onmessage: ((e: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      close = vi.fn()
      constructor() {
        ReadySocket.last = this
        setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({ type: 'ready', run_id: 'r', since: 0 }),
          })
        }, 0)
      }
    }
    vi.stubGlobal('WebSocket', ReadySocket as unknown as typeof WebSocket)

    let body: Record<string, unknown> | null = null
    let release: (() => void) | null = null
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        // Hold the response open so the socket is the only thing on screen —
        // which is the whole point of the feature.
        await held
        return HttpResponse.json({ ...base, model: 'claude', used_llm: true })
      }),
    )

    render(<TutorPane questionId="lr-001" userChoice="A" />)
    await waitFor(() => expect(ReadySocket.last).not.toBeNull())
    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.stream_tokens).toBe(true)
    expect(typeof body!.stream_id).toBe('string')

    ReadySocket.last!.onmessage!({
      data: JSON.stringify({
        type: 'tutor_token',
        question_id: 'lr-001',
        text: 'Contrapositive first.',
        model: 'claude_code/claude-opus-5-5',
        seq: 1,
      }),
    })
    await screen.findByText(/Contrapositive first\./)

    release!()
    // The REST body is authoritative: it replaces the streamed draft.
    await screen.findByText(/inductive leap/)
    vi.unstubAllGlobals()
  })

  // BL-20260503-06: the analysis path has linked its trace since
  // BL-20260502-05; the tutor's walkthrough had no way back to the run that
  // produced it.
  it('links the trace when a collector is configured', async () => {
    const traceId = 'a'.repeat(32)
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', () =>
        HttpResponse.json({
          ...base,
          model: 'mistral:7b-instruct-q4_K_M',
          used_llm: true,
          trace_id: traceId,
          phoenix_trace_url: `https://phoenix.test/traces/${traceId}`,
        }),
      ),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    const link = await screen.findByRole('link', { name: 'Phoenix trace' })
    expect(link).toHaveAttribute(
      'href',
      `https://phoenix.test/traces/${traceId}`,
    )
    expect(link).toHaveAttribute('title', traceId)
  })

  // BL-20260905-79: the reconnect loop was silent. A learner watching a
  // half-written walkthrough could not tell "still coming" from "stuck".
  it('tells the learner when the live stream is interrupted or dropped', async () => {
    class DropSocket {
      static last: DropSocket | null = null
      onmessage: ((e: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      close = vi.fn()
      constructor() {
        DropSocket.last = this
        setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({ type: 'ready', run_id: 'r', since: 0 }),
          })
        }, 0)
      }
    }
    vi.stubGlobal('WebSocket', DropSocket as unknown as typeof WebSocket)

    let release: (() => void) | null = null
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', async () => {
        await held
        return HttpResponse.json({ ...base, model: 'claude', used_llm: true })
      }),
    )

    render(<TutorPane questionId="lr-001" userChoice="A" />)
    await waitFor(() => expect(DropSocket.last).not.toBeNull())
    DropSocket.last!.onmessage!({
      data: JSON.stringify({
        type: 'tutor_token',
        question_id: 'lr-001',
        text: 'Contrapositive first.',
        model: 'claude_code/claude-opus-5-5',
        seq: 1,
      }),
    })
    await screen.findByText(/Contrapositive first\./)

    // The model stopped mid-answer: the draft is wiped, and now it says why
    // instead of leaving a blank pane behind.
    DropSocket.last!.onmessage!({
      data: JSON.stringify({
        type: 'tutor_step',
        stage: 'interrupted',
        question_id: 'lr-001',
        seq: 2,
      }),
    })
    expect(
      await screen.findByText(/The live answer stopped early/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Contrapositive first\./)).not.toBeInTheDocument()

    // And a dropped socket says "reconnecting" rather than nothing at all.
    DropSocket.last!.onclose!()
    expect(await screen.findByText('Reconnecting…')).toBeInTheDocument()

    release!()
    await screen.findByText(/inductive leap/)
    // The notice belongs to the in-flight stream, not to the answer.
    expect(screen.queryByText('Reconnecting…')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('renders no trace link when telemetry is off', async () => {
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', () =>
        HttpResponse.json({
          ...base,
          model: 'mistral:7b-instruct-q4_K_M',
          used_llm: true,
          trace_id: null,
          phoenix_trace_url: null,
        }),
      ),
    )
    render(<TutorPane questionId="lr-001" userChoice="A" />)
    await screen.findByText(/Walkthrough — the inductive leap/)
    expect(
      screen.queryByRole('link', { name: 'Phoenix trace' }),
    ).not.toBeInTheDocument()
  })
})
