/**
 * Keyboard contract for the app shell.
 *
 * Split out as pure functions so the matching rules are unit-testable
 * without mounting the shell, and so every surface agrees on what a key
 * means. The one rule worth stating loudly: a shortcut must never fire while
 * the user is typing. Law AI's primary input is a multi-paragraph fact
 * pattern; swallowing a `[` mid-sentence is a data-loss bug, not a nit.
 */

export type ShellAction =
  | 'toggle-sidebar'
  | 'toggle-inspector'
  | 'open-palette'
  | 'toggle-help'
  | 'dismiss'

export interface KeyLike {
  key: string
  metaKey?: boolean
  ctrlKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
}

const TYPING_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

/** True when `target` is a text-entry surface that owns the keystroke. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || typeof (target as Partial<Element>).tagName !== 'string') {
    return false
  }
  const el = target as HTMLElement
  if (TYPING_TAGS.has(el.tagName)) return true
  return el.isContentEditable === true
}

/**
 * Map a keydown to a shell action, or null when the shell should stay out of
 * the way.
 *
 * `typing` suppresses the plain-key bindings only. Escape and ⌘K stay live
 * while typing on purpose — both are how a user gets *out* of a field, and a
 * dismiss you cannot reach from the search box is worse than no dismiss.
 */
export function matchShortcut(
  event: KeyLike,
  { typing = false }: { typing?: boolean } = {},
): ShellAction | null {
  const mod = event.metaKey === true || event.ctrlKey === true

  if (event.key === 'Escape') return 'dismiss'
  if (mod && (event.key === 'k' || event.key === 'K')) return 'open-palette'

  // Everything below is a bare key: never steal it from a text field, and
  // never from a browser/OS chord the user meant for something else.
  if (typing || mod || event.altKey === true) return null

  if (event.key === '[') return 'toggle-sidebar'
  if (event.key === ']') return 'toggle-inspector'
  if (event.key === '?') return 'toggle-help'

  return null
}

/** Rendered by the `?` help sheet and by the palette's footer hint. */
export const SHORTCUT_HELP: ReadonlyArray<{
  keys: string
  label: string
}> = [
  { keys: '⌘K / Ctrl K', label: 'Open the command palette' },
  { keys: '[', label: 'Toggle the contextual sidebar' },
  { keys: ']', label: 'Toggle the inspector' },
  { keys: '?', label: 'Show this shortcut list' },
  { keys: 'Esc', label: 'Close the palette, a drawer, or this sheet' },
  { keys: 'Tab', label: 'Skip link → main content is the first stop' },
]
