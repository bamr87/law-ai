'use client'

import { useEffect, useLayoutEffect, useRef } from 'react'

import { isTypingTarget } from '@/lib/shell/shortcuts'

/**
 * Window-level keyboard shortcuts for the LSAT drill (BL-20260901-06).
 *
 * A port of `lsat-static/lib/keyboard.ts`, which spec 047 T-015 built for the
 * published static site. The two products drill the same questions, and until
 * this landed they were operated differently: the static site bound A–E,
 * Enter, N/P and H/J/K/R at the window, while the platform bound a subset to
 * one card element — so nothing at all worked until you had tabbed or clicked
 * into that card, and the hint carousel had no keys of its own anywhere.
 *
 * The rules that keep window-level bindings from becoming hostile, kept from
 * the original:
 *
 *  - **Never steal a keystroke from a text field.** The tutor's follow-up box
 *    and the Writing editor are prose; a bare `n` that fired while drafting
 *    would be unusable. Handlers are skipped whenever the event originates in
 *    an input, textarea, select, or contenteditable — unless the binding opts
 *    in with a `mod+` prefix, which no text field claims.
 *  - **Never double-fire.** React attaches its listeners at the root
 *    container, so a component handler that called `preventDefault()` (the
 *    answer radiogroup's roving arrow keys) has already marked the native
 *    event by the time this window listener sees it.
 *  - **Never shadow the browser or a screen reader.** Bare letters and
 *    punctuation only; Alt is left alone, and Ctrl/Cmd only where a binding
 *    explicitly asks for `mod+`.
 *  - **Be listening as soon as the DOM is.** The listener is attached, and the
 *    map ref refreshed, in `useLayoutEffect`. A passive `useEffect` runs on a
 *    later task after a non-discrete commit (a fetch resolving), so a key
 *    pressed the moment a card appeared reached no listener, or a stale map —
 *    the input the drill dropped under load (law-ai#147). Any hook that binds
 *    shortcuts, or syncs a ref a handler reads, has to follow the same rule.
 *
 * What is *not* ported, and deliberately: the shell owns `[`, `]`, `?` and
 * `Escape` on every route (`lib/shell/shortcuts.ts`), so this map refuses
 * them — two window listeners answering the same key is exactly the collision
 * this module has to avoid. The static site has no shell and binds `[`/`]`
 * itself; that is the one divergence, and it is a difference in the chrome,
 * not in the drill.
 */

/** Keys the app shell answers on every route. The drill may never take them. */
export const SHELL_RESERVED_KEYS: ReadonlySet<string> = new Set([
  '[',
  ']',
  '?',
  'Escape',
  'mod+k',
])

export { isTypingTarget }

/**
 * Canonical name for a keystroke: `a`, `Enter`, `mod+Enter`.
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
   * is for the bare keys that are about leaving a field rather than typing
   * into it.
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

/** Test hook: the depth is module state, and a leaked modal is silent. */
export function modalBlockDepth(): number {
  return modalDepth
}

/**
 * True when the keystroke was typed inside an open dialog.
 *
 * The belt to `useModalBlock`'s braces. The shell's command palette and `?`
 * sheet are dialogs this module does not own and cannot make call a hook, and
 * a keystroke aimed at one of them must never also drill the question behind
 * it. Focus is trapped inside an open dialog, so its origin is enough to tell.
 */
function insideDialog(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return target.closest('[role="dialog"], dialog') !== null
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
export function useShortcuts(
  map: ShortcutMap,
  opts: ShortcutOptions = {},
): void {
  const { enabled = true, whileModal = false, allowWhileTyping } = opts
  const allowRef = useRef(allowWhileTyping)
  const mapRef = useRef(map)
  // Layout effects, not passive ones (law-ai#147): see the header.
  useLayoutEffect(() => {
    allowRef.current = allowWhileTyping
    mapRef.current = map
  })

  useLayoutEffect(() => {
    if (!enabled) return
    const onKeyDown = (e: KeyboardEvent) => {
      // A component handler already claimed this keystroke.
      if (e.defaultPrevented) return
      if (modalDepth > 0 && !whileModal) return
      if (!whileModal && insideDialog(e.target)) return
      const name = keyName(e)
      if (SHELL_RESERVED_KEYS.has(name)) return
      const handler = mapRef.current[name]
      if (!handler) return
      // Two deliberate exceptions to the never-steal-from-a-text-field rule:
      // `mod+` bindings (no field claims Ctrl/Cmd+Enter) and any key the
      // caller explicitly allowed.
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
