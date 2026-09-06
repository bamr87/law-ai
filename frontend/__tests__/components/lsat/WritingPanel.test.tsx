/**
 * Argumentative Writing in the platform lab (BL-20260901-09).
 *
 * The behaviours worth pinning are the ones the port could quietly lose: the
 * draft has to survive leaving the prompt, the model response must not be
 * readable before a draft is submitted, and the whole surface has to be
 * operable from the keyboard the way `lsat-static` operates it.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import WritingPanel from '@/components/lsat/WritingPanel'
import { server } from '@/mocks/server'
import { WRITING_DRAFT_PREFIX } from '@/lib/lsat/writingDrafts'

const essay = Array.from({ length: 60 }, (_, i) => `word${i}`).join(' ')

beforeEach(() => {
  window.localStorage.clear()
})

async function openPrompt() {
  render(<WritingPanel />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open prompt' }))
  return screen.findByLabelText('Your response')
}

describe('WritingPanel', () => {
  it('lists the prompts the API serves', async () => {
    render(<WritingPanel />)
    expect(await screen.findByText('Municipal broadband')).toBeInTheDocument()
    expect(
      screen.getByText(/Should the city build its own broadband network/),
    ).toBeInTheDocument()
    expect(screen.getByText(/2 positions · 3 perspectives · 35 min/)).toBeInTheDocument()
  })

  it('says so when no prompts have been authored', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/writing/prompts', () =>
        HttpResponse.json({ prompts: [], count: 0 }),
      ),
    )
    render(<WritingPanel />)
    expect(
      await screen.findByText(/No writing prompts have been authored yet/),
    ).toBeInTheDocument()
  })

  it('opens a prompt with its positions, perspectives and 35-minute clock', async () => {
    await openPrompt()
    expect(screen.getByRole('heading', { name: /build its own broadband/ })).toBeInTheDocument()
    expect(screen.getByText(/A public network is accountable to voters/)).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent('35:00')
    expect(screen.getByText(/pre-writing period \(15 min/)).toBeInTheDocument()
  })

  it('starts and pauses the clock, from the button and from T', async () => {
    await openPrompt()
    const start = screen.getByRole('button', { name: 'Start' })
    fireEvent.click(start)
    expect(await screen.findByRole('button', { name: 'Pause' })).toBeInTheDocument()
    // T is the static site's binding for the same control.
    fireEvent.keyDown(document.body, { key: 't' })
    expect(await screen.findByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('persists the draft in this browser and restores it', async () => {
    const editor = await openPrompt()
    fireEvent.change(editor, { target: { value: 'A first sentence.' } })
    await waitFor(() =>
      expect(
        window.localStorage.getItem(`${WRITING_DRAFT_PREFIX}ws-001`),
      ).toBe('A first sentence.'),
    )

    // Leave the prompt and come back: the draft is still there.
    fireEvent.click(screen.getByRole('button', { name: '← All prompts' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open prompt' }))
    await waitFor(() =>
      expect(screen.getByLabelText('Your response')).toHaveValue(
        'A first sentence.',
      ),
    )
  })

  it('gates submission on a real draft, then unlocks the rubric', async () => {
    const editor = await openPrompt()
    expect(
      screen.getByRole('button', { name: /Submit and unlock feedback/ }),
    ).toBeDisabled()
    expect(screen.getByText(/Write at least 50 words to submit/)).toBeInTheDocument()

    fireEvent.change(editor, { target: { value: essay } })
    const submit = screen.getByRole('button', { name: /Submit and unlock feedback/ })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    // Review: the self-check and the rubric's band notes.
    expect(await screen.findByText('Self-check')).toBeInTheDocument()
    expect(
      screen.getByText(/Can a reader name your position from the first paragraph/),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Band descriptions').length).toBe(2)
  })

  it('submits with Ctrl/⌘+Enter from inside the editor', async () => {
    const editor = await openPrompt()
    fireEvent.change(editor, { target: { value: essay } })
    fireEvent.keyDown(editor, { key: 'Enter', metaKey: true })
    expect(await screen.findByText('Self-check')).toBeInTheDocument()
  })

  it('withholds the model response until the draft is submitted', async () => {
    const editor = await openPrompt()
    // Before submitting there is no reveal control at all, and `M` does
    // nothing — reading the worked example first destroys the exercise.
    expect(
      screen.queryByRole('button', { name: /model response/i }),
    ).not.toBeInTheDocument()
    fireEvent.keyDown(document.body, { key: 'm' })
    await waitFor(() =>
      expect(
        screen.queryByText(/First paragraph of the model essay/),
      ).not.toBeInTheDocument(),
    )

    fireEvent.change(editor, { target: { value: essay } })
    fireEvent.click(screen.getByRole('button', { name: /Submit and unlock feedback/ }))
    await screen.findByText('Self-check')

    fireEvent.keyDown(document.body, { key: 'm' })
    expect(
      await screen.findByText(/First paragraph of the model essay/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/The thesis lands in sentence one/),
    ).toBeInTheDocument()
  })

  it('reads the draft against the rubric and names the model that did it', async () => {
    const editor = await openPrompt()
    fireEvent.change(editor, { target: { value: essay } })
    fireEvent.click(screen.getByRole('button', { name: /Submit and unlock feedback/ }))
    await screen.findByText('Self-check')

    fireEvent.click(
      screen.getByRole('button', { name: /Read my draft against the rubric/ }),
    )
    expect(
      await screen.findByText(/A clear position, thin on the strongest objection/),
    ).toBeInTheDocument()
    // NFR-PROV-1: a machine-derived band says so where it is displayed.
    expect(
      screen.getByText(/Machine-derived · claude_code\/claude-opus-5/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Weighted band 2\.80/)).toBeInTheDocument()
    expect(screen.getByText(/Counterargument · band 2/)).toBeInTheDocument()
  })

  it('opens the first prompt and lands the caret with O', async () => {
    render(<WritingPanel />)
    await screen.findByText('Municipal broadband')
    fireEvent.keyDown(document.body, { key: 'o' })
    const editor = await screen.findByLabelText('Your response')
    await waitFor(() => expect(document.activeElement).toBe(editor))
  })

  it('leaves the editor on Escape, and O brings the caret back', async () => {
    const editor = await openPrompt()
    editor.focus()
    expect(document.activeElement).toBe(editor)
    fireEvent.keyDown(editor, { key: 'Escape' })
    expect(document.activeElement).not.toBe(editor)
    fireEvent.keyDown(document.body, { key: 'o' })
    await waitFor(() => expect(document.activeElement).toBe(editor))
  })

  it('keeps the second Escape out of the way of the shell', async () => {
    // The static site's Escape has a second stage that returns to the prompt
    // list; here the shell owns Escape on every route, so the editor claims
    // only the first press and the way back is the button. The `?` sheet says
    // exactly that (`drillShortcuts.ts`), so the behaviour is pinned rather
    // than left to drift away from its own documentation (BL-20260905-41).
    const editor = await openPrompt()
    editor.focus()
    fireEvent.keyDown(editor, { key: 'Escape' })
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(screen.getByLabelText('Your response')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /All prompts/ }),
    ).toBeInTheDocument()
  })
})
