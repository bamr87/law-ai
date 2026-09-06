/**
 * The LSAT drill's window-level shortcut engine (BL-20260901-06).
 *
 * Ported from `lsat-static/lib/keyboard.ts`, so the rules that keep two
 * products operating the same way are worth pinning here rather than only
 * through the components that use them: never steal a keystroke from a text
 * field, never double-fire behind a component handler, never answer a key the
 * app shell owns.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import {
  isTypingTarget,
  keyName,
  modalBlockDepth,
  useModalBlock,
  useShortcuts,
  SHELL_RESERVED_KEYS,
  type ShortcutMap,
  type ShortcutOptions,
} from '@/lib/lsat/keyboard'

function ev(init: Partial<KeyboardEventInit> & { key: string }): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

function Harness({
  map,
  opts,
}: {
  map: ShortcutMap
  opts?: ShortcutOptions
}) {
  useShortcuts(map, opts)
  return (
    <div>
      <input aria-label="essay" />
      <button type="button">a button</button>
      <div role="dialog" aria-label="sheet">
        <button type="button">in the dialog</button>
      </div>
    </div>
  )
}

describe('keyName', () => {
  it('lower-cases printable characters and keeps named keys as they are', () => {
    expect(keyName(ev({ key: 'N' }))).toBe('n')
    expect(keyName(ev({ key: 'a' }))).toBe('a')
    expect(keyName(ev({ key: 'Enter' }))).toBe('Enter')
    expect(keyName(ev({ key: 'Escape' }))).toBe('Escape')
  })

  it('collapses Ctrl and Cmd to one `mod`, so a binding works on both', () => {
    expect(keyName(ev({ key: 'Enter', ctrlKey: true }))).toBe('mod+Enter')
    expect(keyName(ev({ key: 'Enter', metaKey: true }))).toBe('mod+Enter')
  })

  it('names shift only for named keys — a shifted character is its own key', () => {
    expect(keyName(ev({ key: '?', shiftKey: true }))).toBe('?')
    expect(keyName(ev({ key: 'Tab', shiftKey: true }))).toBe('shift+Tab')
  })
})

describe('isTypingTarget', () => {
  it('is true for the surfaces a user types into', () => {
    render(<Harness map={{}} />)
    expect(isTypingTarget(screen.getByLabelText('essay'))).toBe(true)
    expect(isTypingTarget(screen.getByText('a button'))).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
  })
})

describe('useShortcuts', () => {
  it('fires a bare key anywhere on the page, without a focused card', () => {
    const n = vi.fn()
    render(<Harness map={{ n }} />)
    fireEvent.keyDown(document.body, { key: 'n' })
    expect(n).toHaveBeenCalledTimes(1)
  })

  it('never steals a keystroke from a text field', () => {
    const h = vi.fn()
    render(<Harness map={{ h }} />)
    fireEvent.keyDown(screen.getByLabelText('essay'), { key: 'h' })
    expect(h).not.toHaveBeenCalled()
  })

  it('lets a mod+ binding through a text field, and an explicit opt-in too', () => {
    const submit = vi.fn()
    const leave = vi.fn()
    render(
      <Harness
        map={{ 'mod+Enter': submit, Escape: leave }}
        opts={{ allowWhileTyping: ['Escape'] }}
      />,
    )
    const field = screen.getByLabelText('essay')
    fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true })
    fireEvent.keyDown(field, { key: 'Escape' })
    expect(submit).toHaveBeenCalledTimes(1)
    // Escape is reserved by the shell, so the opt-in cannot resurrect it.
    expect(leave).not.toHaveBeenCalled()
  })

  it('stands down for a keystroke a component handler already claimed', () => {
    const n = vi.fn()
    render(<Harness map={{ n }} />)
    const button = screen.getByText('a button')
    button.addEventListener('keydown', (e) => e.preventDefault())
    fireEvent.keyDown(button, { key: 'n' })
    expect(n).not.toHaveBeenCalled()
  })

  it('refuses the keys the app shell owns on every route', () => {
    const spy = vi.fn()
    const map: ShortcutMap = {}
    for (const key of SHELL_RESERVED_KEYS) map[key] = spy
    render(<Harness map={map} />)
    fireEvent.keyDown(document.body, { key: '[' })
    fireEvent.keyDown(document.body, { key: ']' })
    fireEvent.keyDown(document.body, { key: '?' })
    fireEvent.keyDown(document.body, { key: 'Escape' })
    fireEvent.keyDown(document.body, { key: 'k', metaKey: true })
    expect(spy).not.toHaveBeenCalled()
  })

  it('leaves a keystroke typed inside an open dialog to that dialog', () => {
    const n = vi.fn()
    render(<Harness map={{ n }} />)
    fireEvent.keyDown(screen.getByText('in the dialog'), { key: 'n' })
    expect(n).not.toHaveBeenCalled()
  })

  it('suspends the whole map while a modal is registered', () => {
    const n = vi.fn()
    function Modal() {
      useModalBlock()
      return null
    }
    const view = render(
      <>
        <Harness map={{ n }} />
        <Modal />
      </>,
    )
    expect(modalBlockDepth()).toBe(1)
    fireEvent.keyDown(document.body, { key: 'n' })
    expect(n).not.toHaveBeenCalled()

    view.rerender(<Harness map={{ n }} />)
    expect(modalBlockDepth()).toBe(0)
    fireEvent.keyDown(document.body, { key: 'n' })
    expect(n).toHaveBeenCalledTimes(1)
  })

  it('can be suspended wholesale', () => {
    const n = vi.fn()
    render(<Harness map={{ n }} opts={{ enabled: false }} />)
    fireEvent.keyDown(document.body, { key: 'n' })
    expect(n).not.toHaveBeenCalled()
  })

  it('unbinds on unmount', () => {
    const n = vi.fn()
    const view = render(<Harness map={{ n }} />)
    view.unmount()
    fireEvent.keyDown(document.body, { key: 'n' })
    expect(n).not.toHaveBeenCalled()
  })
})
