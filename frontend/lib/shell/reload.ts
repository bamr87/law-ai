/**
 * Reload the current page.
 *
 * One line, in its own module, for one reason: signing in or out changes what
 * half of this app is willing to fetch, and the components that ask — the
 * scope switcher's matter list, the settings server sync, anything reading the
 * caller's own rows — each ask exactly once per load. Refreshing the router
 * would re-render the server tree and leave every one of those holding the
 * answer it got while anonymous, so the honest move is a full reload
 * (BL-20260906-08). Isolating it also keeps it stubbable: jsdom has no
 * navigation, so a test that exercises sign-in mocks this module rather than
 * fighting `window.location`.
 */
export function reloadPage(): void {
  if (typeof window !== 'undefined') window.location.reload()
}
