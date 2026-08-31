import type { Dock } from '@/lib/settings/catalog'

/**
 * Where a dockable widget should actually render, given the user's preference
 * and what is currently on screen.
 *
 * The preference is a wish, not a guarantee: the `inline` zone only exists on
 * the widget's own module route, and the side panels can be collapsed. A
 * running section clock that silently disappeared because the sidebar was
 * closed would be the worst possible failure of this feature, so the rule is
 * "honour the preference when you can, otherwise show it somewhere" — and
 * `null` only when there is genuinely nowhere to put it.
 */
export function resolveDock(
  preferred: Dock,
  { onOwnRoute, openDocks }: { onOwnRoute: boolean; openDocks: Dock[] },
): Dock | null {
  // The page itself is always available on its own route.
  const available: Dock[] = onOwnRoute
    ? [...openDocks.filter((d) => d !== 'inline'), 'inline']
    : openDocks.filter((d) => d !== 'inline')

  if (available.includes(preferred)) return preferred
  return available[0] ?? null
}
