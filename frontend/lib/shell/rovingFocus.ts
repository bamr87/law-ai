/**
 * Roving-tabindex key handling for composite widgets (tabs, radiogroups).
 *
 * Split out as a pure function so the keyboard contract is unit-testable
 * without mounting a widget, and so every composite widget in the app agrees
 * on what an arrow key means.
 *
 * The rule this encodes (WAI-ARIA Authoring Practices): a composite widget is
 * ONE tab stop. Tab moves to it, arrows move *within* it. Seven tabs that are
 * seven tab stops is not a tab bar — it is a list of buttons wearing
 * `role="tab"`, and it makes a screen-reader user page through the whole
 * switcher to reach the content.
 */

export type RovingOrientation = 'horizontal' | 'vertical' | 'both'

export interface RovingKeyEvent {
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
}

const NEXT_KEYS: Record<RovingOrientation, string[]> = {
  horizontal: ['ArrowRight'],
  vertical: ['ArrowDown'],
  both: ['ArrowRight', 'ArrowDown'],
}

const PREV_KEYS: Record<RovingOrientation, string[]> = {
  horizontal: ['ArrowLeft'],
  vertical: ['ArrowUp'],
  both: ['ArrowLeft', 'ArrowUp'],
}

/**
 * Index the focus should move to, or `null` when the key is not ours and the
 * event must be left alone.
 *
 * Wraps at both ends: a tab bar that dead-ends makes the user reverse out of
 * it, and Home/End exist precisely so long groups stay one keystroke deep.
 */
export function nextRovingIndex(
  event: RovingKeyEvent,
  current: number,
  count: number,
  {
    orientation = 'horizontal',
    loop = true,
  }: { orientation?: RovingOrientation; loop?: boolean } = {},
): number | null {
  if (count <= 0) return null
  // Never steal a browser or OS chord — Ctrl/Cmd+Arrow is word-jump, desktop
  // switching, or history navigation depending on the platform.
  if (event.ctrlKey || event.metaKey || event.altKey) return null

  const clamped = current < 0 || current >= count ? 0 : current

  if (NEXT_KEYS[orientation].includes(event.key)) {
    const n = clamped + 1
    return n >= count ? (loop ? 0 : count - 1) : n
  }
  if (PREV_KEYS[orientation].includes(event.key)) {
    const p = clamped - 1
    return p < 0 ? (loop ? count - 1 : 0) : p
  }
  if (event.key === 'Home') return 0
  if (event.key === 'End') return count - 1

  return null
}
