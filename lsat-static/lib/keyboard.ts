'use client'

import { useEffect, useRef } from 'react'

/**
 * Window-level keyboard shortcuts for the practice app.
 *
 * The exam is timed, so every step of a drill has to be reachable without
 * moving a hand to the mouse or tabbing through chrome to find a button. The
 * rules that keep that from becoming hostile:
 *
 *  - **Never steal a keystroke from a text field.** The Writing section is a
 *    35-minute essay; a bare `n` shortcut that fired while drafting would be
 *    unusable. Handlers are skipped whenever the event originates in an
 *    input, textarea, select, or contenteditable — unless the binding opts in
 *    with a `mod+` prefix, which no text field claims.
 *  - **Never double-fire.** React attaches its listeners at the root
 *    container, so a component handler that calls `preventDefault()` (the
 *    answer radiogroup's Arrow/Enter handling) has already marked the native
 *    event by the time this window listener sees it.
 *  - **Never shadow the browser or a screen reader.** Bare letters and
 *    punctuation only; anything with Alt is left alone, and Ctrl/Cmd is used
 *    only where a binding explicitly asks for `mod+`.
 */

/** True when the keystroke belongs to something the user is typing into. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

/**
 * Canonical name for a keystroke: `a`, `?`, `Enter`, `Escape`, `mod+Enter`.
 *
 * Ctrl and Cmd collapse to one `mod` so a binding works on both platforms.
 * Shift is only part of the name for named keys — for printable characters
 * the shifted character *is* the key (`?` rather than `shift+/`).
 */
export function keyName(e: KeyboardEvent): string {
  const parts: string[] = []
  if (e.ctrlKey || e.metaKey) parts.push('mod')
  if (e.altKey) parts.push('alt')
  if (e.shiftKey && e.key.length > 1) parts.push('shift')
  parts.push(e.key.length === 1 ? e.key.toLowerCase() : e.key)
  return parts.join('+')
}

export type ShortcutHandler = (e: KeyboardEvent) => void
export type ShortcutMap = Record<string, ShortcutHandler>

export interface ShortcutOptions {
  /** Set false to suspend the whole map. */
  enabled?: boolean
  /**
   * Keystrokes that may fire even when a text field has focus.
   *
   * `mod+` bindings are always allowed (no field claims Ctrl/Cmd+Enter). This
   * is for the bare keys that are genuinely about leaving a field rather than
   * typing into it — `Escape` above all, which is otherwise blocked by the
   * very guard that exists to protect the writing editor.
   */
  allowWhileTyping?: string[]
  /**
   * Keep firing while a modal is open. Off by default: a dialog that let the
   * page behind it keep answering keystrokes would be modal in appearance
   * only. Only the bindings that operate the dialog itself opt in.
   */
  whileModal?: boolean
}

// Open-modal depth. Checked when a key is pressed rather than when the
// listener is bound, because opening a dialog must suspend maps that were
// bound long before it existed.
let modalDepth = 0

/** Register a modal for as long as the component is mounted. */
export function useModalBlock(active = true): void {
  useEffect(() => {
    if (!active) return
    modalDepth += 1
    return () => {
      modalDepth -= 1
    }
  }, [active])
}

/**
 * Bind a map of shortcuts for as long as the component is mounted.
 *
 * The map is read through a ref, so handlers always see current state without
 * the listener being torn down and rebuilt on every render.
 *
 * @param map   keystroke name (see {@link keyName}) → handler
 * @param opts  see {@link ShortcutOptions}
 */
export function useShortcuts(map: ShortcutMap, opts: ShortcutOptions = {}): void {
  const { enabled = true, whileModal = false, allowWhileTyping } = opts
  const allowRef = useRef(allowWhileTyping)
  const mapRef = useRef(map)
  // Written from an effect, not during render, exactly as the platform hook
  // does it (frontend/lib/lsat/keyboard.ts) — a ref mutated in the render body
  // is a rules-of-React violation the new lint gate rejects (BL-20260905-15).
  useEffect(() => {
    allowRef.current = allowWhileTyping
    mapRef.current = map
  })

  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (e: KeyboardEvent) => {
      // A component handler already claimed this keystroke.
      if (e.defaultPrevented) return
      if (modalDepth > 0 && !whileModal) return
      const name = keyName(e)
      const handler = mapRef.current[name]
      if (!handler) return
      // Two deliberate exceptions to the never-steal-from-a-text-field rule:
      // `mod+` bindings (no field claims Ctrl/Cmd+Enter, which is how Writing
      // submits) and any key the caller explicitly allowed.
      const allowed =
        name.startsWith('mod+') || (allowRef.current?.includes(name) ?? false)
      if (isTypingTarget(e.target) && !allowed) return
      e.preventDefault()
      handler(e)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled, whileModal])
}
