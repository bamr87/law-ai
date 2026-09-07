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

export interface ShortcutRow {
  keys: string
  label: string
}

/**
 * A titled block of rows in the `?` sheet.
 *
 * The sheet used to be one flat list of the four shell chords, so the keys a
 * *page* binds — the LSAT drill's A–E, Enter, N — were undiscoverable outside
 * the card's own hint line (BL-20260901-10). A page registers its group while
 * it is on screen; the shell's own group always comes first, because those
 * keys work everywhere and the page's do not.
 */
export interface ShortcutGroup {
  title: string
  rows: ReadonlyArray<ShortcutRow>
}

/** Rendered by the `?` help sheet and by the palette's footer hint. */
export const SHORTCUT_HELP: ReadonlyArray<ShortcutRow> = [
  { keys: '⌘K / Ctrl K', label: 'Open the command palette' },
  { keys: '[', label: 'Toggle the contextual sidebar' },
  { keys: ']', label: 'Toggle the inspector' },
  { keys: '?', label: 'Show this shortcut list' },
  { keys: 'Esc', label: 'Close the palette, a drawer, or this sheet' },
  { keys: 'Tab', label: 'Skip link → main content is the first stop' },
]

/** The shell's own keys — the group that is true on every route. */
export const SHELL_SHORTCUTS: ShortcutGroup = {
  title: 'Anywhere',
  rows: SHORTCUT_HELP,
}

/**
 * The sheet's contents: the shell's group, then whatever the page registered.
 *
 * Pure, so the ordering contract is testable without mounting the shell.
 * Empty groups are dropped and a title never appears twice — several cards on
 * one screen (an RC passage stacks them) register the same group.
 */
export function mergeShortcutGroups(
  pageGroups: ReadonlyArray<ShortcutGroup>,
): ShortcutGroup[] {
  const merged: ShortcutGroup[] = [SHELL_SHORTCUTS]
  const seen = new Set<string>([SHELL_SHORTCUTS.title])
  for (const group of pageGroups) {
    if (group.rows.length === 0 || seen.has(group.title)) continue
    seen.add(group.title)
    merged.push(group)
  }
  return merged
}
