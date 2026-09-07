/**
 * Panel open/closed resolution for the app shell.
 *
 * The URL is the source of truth so a panel layout is linkable, survives a
 * refresh, and is restored by the browser's own history — a panel state kept
 * only in React is a state a user cannot share or get back with Back.
 * The stored preference is the *fallback* for a URL that says nothing.
 */

export type PanelKey = 'sidebar' | 'inspector'

export const PANEL_KEYS: readonly PanelKey[] = ['sidebar', 'inspector']

/**
 * Query keys are a shared namespace. The shell owns `sidebar` and `inspector`;
 * screens own the view keys in `lib/shell/viewState.ts` (`tab`, `type`, `q`,
 * `case`) and reach them only through `useUrlState`/`useUrlText`, which start
 * from the current params and touch one key — so a screen can never clobber
 * the panel layout, and two screens cannot mean different things by `tab`
 * (BL-20260831-02).
 */

/**
 * Resolve one panel. `?sidebar=1` / `?sidebar=0` win; anything else (absent,
 * or a value we don't recognise) falls back to the caller's preference so a
 * mangled URL degrades to the default instead of a blank shell.
 */
export function panelOpen(
  params: URLSearchParams,
  key: PanelKey,
  fallback: boolean,
): boolean {
  const v = params.get(key)
  if (v === '0') return false
  if (v === '1') return true
  return fallback
}

/** Next query string with one panel forced open/closed. */
export function withPanel(
  params: URLSearchParams,
  key: PanelKey,
  open: boolean,
): string {
  const next = new URLSearchParams(params.toString())
  next.set(key, open ? '1' : '0')
  return next.toString()
}

/** `pathname` + query, with an empty query collapsing to the bare path. */
export function panelHref(pathname: string, query: string): string {
  return query ? `${pathname}?${query}` : pathname
}

/** Next query string with both panel params dropped — the URL half of a layout reset. */
export function withoutPanels(params: URLSearchParams): string {
  const next = new URLSearchParams(params.toString())
  for (const key of PANEL_KEYS) next.delete(key)
  return next.toString()
}
