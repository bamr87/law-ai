/**
 * The writing section's keyboard contract (BL-20260901-07).
 *
 * The essay is the hardest place on the site to get shortcuts right: it is a
 * 35-minute text field, so the never-steal-from-a-text-field guard is doing
 * exactly its job, and every key that has to work *while* drafting must be an
 * explicit exception. Both known defects lived here — `Escape` blocked by the
 * typing guard, and `O` opening a prompt without reaching the editor — so both
 * get a test that presses the key rather than reading the source.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Writing from '@/components/Writing'
import { LONG_DRAFT } from './fixtures'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    sectionMeta: () => f.SECTION_WS,
    writingPrompts: [f.PROMPT, f.PROMPT_B],
    rubricFor: () => f.RUBRIC,
  }
})

function editor(): HTMLTextAreaElement {
  return screen.getByRole('textbox') as HTMLTextAreaElement
}

function type(text: string): void {
  fireEvent.change(editor(), { target: { value: text } })
}

describe('Writing keyboard flow', () => {
  it('opens the first prompt with O and puts the caret in the editor', () => {
    // O is the only key into the section; opening a prompt but leaving focus
    // six Tab stops from the textarea made it useless on its own.
    render(<Writing />)
    expect(screen.getAllByRole('button', { name: 'Open prompt' })).toHaveLength(2)

    fireEvent.keyDown(window, { key: 'o' })
    expect(screen.getByRole('heading', { name: 'Should the town build the bypass?' }))
      .toBeInTheDocument()
    expect(document.activeElement).toBe(editor())
  })

  it('leaves focus alone when a prompt is opened with the mouse', () => {
    // The click already put the reader where they meant to be; yanking focus
    // to the textarea would scroll the prompt they came to read off screen.
    render(<Writing />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Open prompt' })[1])
    expect(
      screen.getByRole('navigation', { name: 'Writing navigation' }),
    ).toHaveTextContent('Fixture prompt two')
    expect(document.activeElement).not.toBe(editor())
  })

  it('Escape blurs the editor first and only leaves on a second press', () => {
    // Regression: the typing guard blocked Escape entirely, so the essay had
    // no keyboard exit at all. And a single Escape that jumped back to the
    // list would discard the workspace from under someone who only wanted out
    // of the field to reach another shortcut.
    render(<Writing />)
    fireEvent.keyDown(window, { key: 'o' })
    const field = editor()
    expect(document.activeElement).toBe(field)

    fireEvent.keyDown(field, { key: 'Escape' })
    expect(document.activeElement).not.toBe(field)
    expect(screen.getByRole('textbox')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getAllByRole('button', { name: 'Open prompt' })).toHaveLength(2)
  })

  it('O returns to the editor after Escape has left it', () => {
    render(<Writing />)
    fireEvent.keyDown(window, { key: 'o' })
    fireEvent.keyDown(editor(), { key: 'Escape' })
    expect(document.activeElement).not.toBe(editor())
    fireEvent.keyDown(window, { key: 'o' })
    expect(document.activeElement).toBe(editor())
  })

  it('T works the clock, but never while the essay has focus', () => {
    render(<Writing />)
    fireEvent.keyDown(window, { key: 'o' })
    const field = editor()
    const clock = screen.getByRole('button', { name: 'Start' })

    // A bare `t` inside a 35-minute essay is a letter, not a shortcut.
    fireEvent.keyDown(field, { key: 't' })
    expect(clock).toHaveTextContent('Start')

    fireEvent.keyDown(field, { key: 'Escape' })
    fireEvent.keyDown(window, { key: 't' })
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 't' })
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
  })

  it('submits with mod+Enter from inside the editor, once the draft is long enough', () => {
    // The one binding that fires while typing: no text field claims
    // Ctrl/Cmd+Enter, and a bare key would be swallowed by the essay.
    const onAnnounce = vi.fn()
    render(<Writing onAnnounce={onAnnounce} />)
    fireEvent.keyDown(window, { key: 'o' })

    type('too short')
    fireEvent.keyDown(editor(), { key: 'Enter', metaKey: true })
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(onAnnounce).not.toHaveBeenCalled()

    type(LONG_DRAFT)
    fireEvent.keyDown(editor(), { key: 'Enter', ctrlKey: true })
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.getByRole('region', { name: 'Review' })).toBeInTheDocument()
    expect(onAnnounce).toHaveBeenCalledWith(
      'Draft submitted. Rubric and model response unlocked.',
    )
  })

  it('M shows and hides the model response once the draft is in', () => {
    render(<Writing />)
    fireEvent.keyDown(window, { key: 'o' })
    type(LONG_DRAFT)
    fireEvent.keyDown(editor(), { key: 'Enter', metaKey: true })

    expect(screen.queryByText('The bypass is worth its cost.')).toBeNull()
    fireEvent.keyDown(window, { key: 'm' })
    const thesis = screen.getByText('The bypass is worth its cost.')
    expect(thesis.closest('article')).toHaveTextContent(
      'The thesis is in sentence one.',
    )
    fireEvent.keyDown(window, { key: 'm' })
    expect(screen.queryByText('The bypass is worth its cost.')).toBeNull()
  })
})

/**
 * The three things the writing view does that nothing else on the site does
 * (BL-20260831-26): a 35-minute clock, a draft that survives the browser
 * being closed, and feedback that stays locked until the draft is in. All
 * three were verified structurally by the root suite and by hand until the
 * runner landed.
 */
describe('Writing workspace', () => {
  const DRAFT_KEY = 'lsat-writing:draft:ws-fixture-01'
  const DONE_KEY = 'lsat-writing:submitted:ws-fixture-01'

  function openPrompt(): void {
    fireEvent.keyDown(window, { key: 'o' })
  }

  describe('the 35-minute clock', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('counts the prompt’s own limit down and stops itself at zero', () => {
      render(<Writing />)
      openPrompt()
      const clock = screen.getByRole('timer')
      expect(clock).toHaveTextContent('35:00')
      // Nothing moves until the reader starts it: the pre-writing period is
      // part of the exercise.
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
      expect(clock).toHaveTextContent('35:00')

      fireEvent.click(screen.getByRole('button', { name: 'Start' }))
      act(() => {
        vi.advanceTimersByTime(30 * 60_000)
      })
      expect(clock).toHaveTextContent('5:00')
      // The last five minutes are marked, not just counted.
      expect(clock.className).toContain('section-timer-urgent')

      act(() => {
        vi.advanceTimersByTime(5 * 60_000)
      })
      expect(clock).toHaveTextContent('0:00')
      expect(clock.className).toContain('section-timer-expired')
      // Expiry stops the clock rather than running negative, and there is
      // nothing left to start.
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
      expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled()
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
      expect(clock).toHaveTextContent('0:00')
    })

    it('resets to the full limit', () => {
      render(<Writing />)
      openPrompt()
      fireEvent.click(screen.getByRole('button', { name: 'Start' }))
      act(() => {
        vi.advanceTimersByTime(90_000)
      })
      expect(screen.getByRole('timer')).toHaveTextContent('33:30')
      fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
      expect(screen.getByRole('timer')).toHaveTextContent('35:00')
      expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
    })
  })

  describe('the draft', () => {
    it('is written to this browser and read back on the way in', () => {
      const first = render(<Writing />)
      openPrompt()
      type('A first pass at the argument.')
      expect(window.localStorage.getItem(DRAFT_KEY)).toBe(
        'A first pass at the argument.',
      )
      // A closed tab, a reload, a crash: the workspace is rebuilt from
      // storage, not from React state.
      first.unmount()

      render(<Writing />)
      openPrompt()
      expect(editor()).toHaveValue('A first pass at the argument.')
    })

    it('remembers that a prompt was submitted, and reopens in review', () => {
      const first = render(<Writing />)
      openPrompt()
      type(LONG_DRAFT)
      fireEvent.keyDown(editor(), { key: 'Enter', metaKey: true })
      expect(window.localStorage.getItem(DONE_KEY)).toBe('1')
      first.unmount()

      render(<Writing />)
      openPrompt()
      // Straight past the editor: the draft is in, so the feedback is what is
      // left to do.
      expect(screen.queryByRole('textbox')).toBeNull()
      expect(screen.getByRole('region', { name: 'Review' })).toBeInTheDocument()
      expect(screen.getByText(LONG_DRAFT)).toBeInTheDocument()
    })

    it('keeps each prompt’s draft separate', () => {
      render(<Writing />)
      fireEvent.click(screen.getAllByRole('button', { name: 'Open prompt' })[1])
      type('Notes on the second prompt.')
      expect(window.localStorage.getItem('lsat-writing:draft:ws-fixture-02')).toBe(
        'Notes on the second prompt.',
      )
      expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull()
    })

    it('survives storage being unavailable', () => {
      // Private browsing and blocked site data both throw on access; a lost
      // draft is a worse outcome than a lost feature, but neither may break
      // the page.
      const getItem = vi
        .spyOn(Storage.prototype, 'getItem')
        .mockImplementation(() => {
          throw new Error('blocked')
        })
      const setItem = vi
        .spyOn(Storage.prototype, 'setItem')
        .mockImplementation(() => {
          throw new Error('blocked')
        })
      try {
        render(<Writing />)
        openPrompt()
        type('Drafting anyway.')
        expect(editor()).toHaveValue('Drafting anyway.')
      } finally {
        getItem.mockRestore()
        setItem.mockRestore()
      }
    })
  })

  describe('feedback stays locked until the draft is in', () => {
    it('withholds the rubric bands and the model response while drafting', () => {
      // Both ship in the bundle from the first byte — there is no server to
      // withhold them — so the lock is the UI's job. Reading the worked
      // example first turns it into a template rather than a comparison.
      render(<Writing />)
      openPrompt()
      expect(screen.queryByText('The bypass is worth its cost.')).toBeNull()
      expect(screen.queryByText('Band descriptions')).toBeNull()
      expect(screen.queryByText('Did you state a position?')).toBeNull()
      expect(
        screen.queryByRole('button', { name: /model response/i }),
      ).toBeNull()
    })

    it('unlocks the self-check, the bands and the model response on submit', () => {
      const onAnnounce = vi.fn()
      render(<Writing onAnnounce={onAnnounce} />)
      openPrompt()

      // Fewer than 50 words is not a draft, and the button says so.
      type('Three words only')
      expect(screen.getByRole('button', { name: /Submit and unlock/ })).toBeDisabled()
      expect(screen.getByText('Write at least 50 words to submit.')).toBeInTheDocument()

      type(LONG_DRAFT)
      fireEvent.click(screen.getByRole('button', { name: /Submit and unlock/ }))

      expect(screen.getByText('Did you state a position?')).toBeInTheDocument()
      expect(screen.getByText('Band descriptions')).toBeInTheDocument()
      expect(screen.getByText('Four criteria, four bands.')).toBeInTheDocument()
      expect(onAnnounce).toHaveBeenCalledWith(
        'Draft submitted. Rubric and model response unlocked.',
      )

      // The model response is one further, deliberate click past the rubric.
      expect(screen.queryByText('The bypass is worth its cost.')).toBeNull()
      const reveal = screen.getByRole('button', {
        name: 'Show the annotated model response',
      })
      expect(reveal).toHaveAttribute('aria-expanded', 'false')
      fireEvent.click(reveal)
      expect(screen.getByText('The bypass is worth its cost.')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Hide model response' }),
      ).toHaveAttribute('aria-expanded', 'true')
    })
  })
})
