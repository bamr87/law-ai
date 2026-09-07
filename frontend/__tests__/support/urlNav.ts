import { vi } from 'vitest'

/**
 * A live stand-in for the App Router's URL, for screens whose view state is in
 * the query string (BL-20260831-02).
 *
 * `vi.fn()` router mocks are enough to assert *that* a screen navigated, but
 * not that it re-renders from the new URL — and reading the tab back out of
 * the URL is the whole feature. So this store keeps the params, notifies
 * subscribers on a push/replace, and the mocked `useSearchParams` reads it
 * through `useSyncExternalStore`: a click really does change the URL and the
 * component really does re-render from it, the way it will in the browser.
 *
 * Use it as:
 *
 * ```ts
 * const nav = createNavStore('/lsat')
 * vi.mock('next/navigation', async () => {
 *   const { useSyncExternalStore } = await import('react')
 *   return {
 *     usePathname: () => nav.path,
 *     useSearchParams: () =>
 *       useSyncExternalStore(nav.subscribe, nav.read, nav.read),
 *     useRouter: () => ({ push: nav.push, replace: nav.replace }),
 *   }
 * })
 * ```
 *
 * Every reference to `nav` stays inside a closure: `vi.mock` is hoisted above
 * this module's own initialisation, so a factory that dereferenced the store
 * eagerly would run into the temporal dead zone.
 */
export interface NavStore {
  path: string
  read: () => URLSearchParams
  subscribe: (listener: () => void) => () => void
  /** Set the query string directly, as a test arranging its starting URL. */
  set: (query: string) => void
  push: ReturnType<typeof vi.fn>
  replace: ReturnType<typeof vi.fn>
  /** The hrefs pushed or replaced, oldest first. */
  hrefs: string[]
  reset: (query?: string) => void
}

export function createNavStore(path: string, query = ''): NavStore {
  let params = new URLSearchParams(query)
  const listeners = new Set<() => void>()

  const emit = () => {
    for (const l of listeners) l()
  }
  const set = (next: string) => {
    params = new URLSearchParams(next)
    emit()
  }
  const navigate = (href: string) => {
    store.hrefs.push(href)
    set(href.split('?')[1] ?? '')
  }

  const store: NavStore = {
    path,
    read: () => params,
    subscribe: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    set,
    push: vi.fn(navigate),
    replace: vi.fn(navigate),
    hrefs: [],
    reset: (q = '') => {
      store.hrefs.length = 0
      store.push.mockClear()
      store.replace.mockClear()
      set(q)
    },
  }
  return store
}
