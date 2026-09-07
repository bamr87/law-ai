/**
 * The shortcut layer itself (BL-20260901-07).
 *
 * Every binding on this site used to be verified by pressing keys in a browser
 * by hand, which is how the two defects pinned below were found *and* how they
 * would have come back unnoticed:
 *
 *  1. **Enter starvation.** `useShortcuts` calls `preventDefault()` before it
 *     dispatches, and skips an event another listener already claimed. A map
 *     that binds `Enter` permanently therefore swallows the key even when its
 *     handler no-ops — which is what starved Drill's Enter-to-advance while
 *     QuestionCard still had a bound-but-inert `Enter`.
 *  2. **Escape trapped in the editor.** The never-steal-from-a-text-field guard
 *     blocked the one key whose entire job is leaving a text field, so the
 *     35-minute writing editor had no keyboard exit.
 *
 * These are unit tests over the hook. The bindings as the reader meets them are
 * in Drill.test.tsx, Writing.test.tsx, SolveAssist.test.tsx and
 * focus-contract.test.tsx.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { ShortcutMap, ShortcutOptions } from '@/lib/keyboard'
import { isTypingTarget, keyName, useModalBlock, useShortcuts } from '@/lib/keyboard'

/** Binds a map for as long as it is mounted, and renders nothing. */
function Bind({ map, opts }: { map: ShortcutMap; opts?: ShortcutOptions }) {
  useShortcuts(map, opts)
  return null
}

/** Stands in for an open dialog: suspends every map that is not `whileModal`. */
function Modal() {
  useModalBlock()
  return null
}

function ev(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

describe('keyName', () => {
  it('names a printable key by the character, not by the chord that made it', () => {
    // `?` is Shift+/ on most layouts; the shifted character *is* the key, so a
    // binding written as '?' must not have to know about Shift.
    expect(keyName(ev({ key: '?', shiftKey: true }))).toBe('?')
    expect(keyName(ev({ key: 'A', shiftKey: true }))).toBe('a')
    expect(keyName(ev({ key: 'n' }))).toBe('n')
  })

  it('collapses Ctrl and Cmd into one `mod` so a binding works on both platforms', () => {
    expect(keyName(ev({ key: 'Enter', ctrlKey: true }))).toBe('mod+Enter')
    expect(keyName(ev({ key: 'Enter', metaKey: true }))).toBe('mod+Enter')
  })

  it('keeps Shift and Alt on named keys', () => {
    expect(keyName(ev({ key: 'Tab', shiftKey: true }))).toBe('shift+Tab')
    expect(keyName(ev({ key: 'n', altKey: true }))).toBe('alt+n')
    expect(keyName(ev({ key: 'Escape' }))).toBe('Escape')
  })
})

describe('isTypingTarget', () => {
  it('recognises every field a keystroke could belong to', () => {
    render(
      <div>
        <input aria-label="field" />
        <textarea aria-label="essay" />
        <select aria-label="picker">
          <option>one</option>
        </select>
        <button type="button">press</button>
      </div>,
    )
    expect(isTypingTarget(screen.getByLabelText('field'))).toBe(true)
    expect(isTypingTarget(screen.getByLabelText('essay'))).toBe(true)
    expect(isTypingTarget(screen.getByLabelText('picker'))).toBe(true)
    expect(isTypingTarget(screen.getByRole('button', { name: 'press' }))).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
  })

  it('recognises a contenteditable host', () => {
    // jsdom does not implement `isContentEditable` (it is always false there,
    // whatever the attribute says), so the property is stubbed rather than the
    // element authored — the branch is still the one the browser takes.
    const editable = document.createElement('div')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    expect(isTypingTarget(editable)).toBe(true)
  })
})

describe('useShortcuts', () => {
  it('runs a bound handler and claims the keystroke', () => {
    const onN = vi.fn()
    render(<Bind map={{ n: onN }} />)
    // fireEvent returns false when the event was cancelled.
    expect(fireEvent.keyDown(window, { key: 'n' })).toBe(false)
    expect(onN).toHaveBeenCalledTimes(1)
  })

  it('leaves an unbound keystroke alone', () => {
    // Load-bearing: this is what lets the browser keep its own keys, and what
    // lets two components share `Enter` by binding it only when they can act.
    render(<Bind map={{ n: vi.fn() }} />)
    expect(fireEvent.keyDown(window, { key: 'q' })).toBe(true)
  })

  it('skips an event another handler already claimed', () => {
    // Regression: a permanently-bound key starves every later listener for it.
    const first = vi.fn()
    const second = vi.fn()
    render(
      <>
        <Bind map={{ Enter: first }} />
        <Bind map={{ Enter: second }} />
      </>,
    )
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).not.toHaveBeenCalled()
  })

  it('hands the key on when the first map declines to bind it', () => {
    // ...which is why QuestionCard binds `{}` once a question is graded
    // instead of binding an `Enter` whose handler merely no-ops.
    const second = vi.fn()
    render(
      <>
        <Bind map={{}} />
        <Bind map={{ Enter: second }} />
      </>,
    )
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('never steals a bare key from a text field', () => {
    const onN = vi.fn()
    render(
      <>
        <textarea aria-label="essay" />
        <Bind map={{ n: onN }} />
      </>,
    )
    const essay = screen.getByLabelText('essay')
    expect(fireEvent.keyDown(essay, { key: 'n' })).toBe(true)
    expect(onN).not.toHaveBeenCalled()
    // The same key outside a field still works.
    fireEvent.keyDown(window, { key: 'n' })
    expect(onN).toHaveBeenCalledTimes(1)
  })

  it('lets `mod+` bindings through a text field', () => {
    // No field claims Ctrl/Cmd+Enter, which is how the writing editor submits.
    const onSubmit = vi.fn()
    render(
      <>
        <textarea aria-label="essay" />
        <Bind map={{ 'mod+Enter': onSubmit }} />
      </>,
    )
    fireEvent.keyDown(screen.getByLabelText('essay'), { key: 'Enter', metaKey: true })
    fireEvent.keyDown(screen.getByLabelText('essay'), { key: 'Enter', ctrlKey: true })
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it('lets an explicitly allowed key out of a text field', () => {
    // Regression: the typing guard blocked `Escape`, the one key whose whole
    // job is leaving the field, so the essay editor had no keyboard exit.
    const onEscape = vi.fn()
    const onOther = vi.fn()
    render(
      <>
        <textarea aria-label="essay" />
        <Bind map={{ Escape: onEscape, o: onOther }} opts={{ allowWhileTyping: ['Escape'] }} />
      </>,
    )
    const essay = screen.getByLabelText('essay')
    fireEvent.keyDown(essay, { key: 'Escape' })
    expect(onEscape).toHaveBeenCalledTimes(1)
    // Only the allow-list gets out; `o` is still typing.
    fireEvent.keyDown(essay, { key: 'o' })
    expect(onOther).not.toHaveBeenCalled()
  })

  it('suspends the whole map when disabled', () => {
    const onSlash = vi.fn()
    render(<Bind map={{ '/': onSlash }} opts={{ enabled: false }} />)
    expect(fireEvent.keyDown(window, { key: '/' })).toBe(true)
    expect(onSlash).not.toHaveBeenCalled()
  })

  it('suspends page bindings while a modal is open, but not the modal’s own', () => {
    const page = vi.fn()
    const dialog = vi.fn()
    const { rerender } = render(
      <>
        <Bind map={{ Escape: page }} />
        <Bind map={{ Escape: dialog }} opts={{ whileModal: true }} />
      </>,
    )
    // No modal yet: the page map claims it first.
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(page).toHaveBeenCalledTimes(1)
    expect(dialog).not.toHaveBeenCalled()

    rerender(
      <>
        <Bind map={{ Escape: page }} />
        <Bind map={{ Escape: dialog }} opts={{ whileModal: true }} />
        <Modal />
      </>,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(page).toHaveBeenCalledTimes(1)
    expect(dialog).toHaveBeenCalledTimes(1)

    // Closing the dialog hands the page its keys back.
    rerender(
      <>
        <Bind map={{ Escape: page }} />
        <Bind map={{ Escape: dialog }} opts={{ whileModal: true }} />
      </>,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(page).toHaveBeenCalledTimes(2)
  })

  it('reads the map through a ref, so a handler sees current state', () => {
    // The listener is bound once; a stale closure here would make every
    // shortcut act on the state the component had when it mounted.
    function Counter() {
      const [n, setN] = useState(0)
      useShortcuts({ n: () => setN((v) => v + 1), r: () => setN(n) })
      return <output>{n}</output>
    }
    render(<Counter />)
    fireEvent.keyDown(window, { key: 'n' })
    fireEvent.keyDown(window, { key: 'n' })
    expect(screen.getByRole('status')).toHaveTextContent('2')
    // `r` re-sets from the value captured at the current render, not at mount.
    fireEvent.keyDown(window, { key: 'r' })
    expect(screen.getByRole('status')).toHaveTextContent('2')
  })

  it('stops listening once unmounted', () => {
    const onN = vi.fn()
    const { unmount } = render(<Bind map={{ n: onN }} />)
    unmount()
    expect(fireEvent.keyDown(window, { key: 'n' })).toBe(true)
    expect(onN).not.toHaveBeenCalled()
  })
})
