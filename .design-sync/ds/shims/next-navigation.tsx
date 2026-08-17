// Browser-safe stand-in for `next/navigation`.
//
// The real module requires an App Router runtime and reads `process.env.__NEXT_*`
// at module scope, so importing it poisons the whole bundle (see ../process-shim.ts).
// NavBar is the only consumer, and it uses `usePathname()` purely to decide which
// nav item is active.
//
// `usePathname()` reads `window.__LAWAI_PATHNAME` when set, so a preview can
// render the nav's active state for any route by assigning that global before
// mount; it falls back to '/' — the same value NavBar's own `|| '/'` guard uses.
//
// Wired in via `compilerOptions.paths` in ../tsconfig.json.

declare global {
  interface Window {
    __LAWAI_PATHNAME?: string;
  }
}

/** Current path. Override for previews with `window.__LAWAI_PATHNAME = '/agents'`. */
export function usePathname(): string {
  if (typeof window !== 'undefined' && typeof window.__LAWAI_PATHNAME === 'string') {
    return window.__LAWAI_PATHNAME;
  }
  return '/';
}

export function useSearchParams(): URLSearchParams {
  return new URLSearchParams(
    typeof window !== 'undefined' ? window.location.search : '',
  );
}

export function useParams<T extends Record<string, string | string[]> = Record<string, string>>(): T {
  return {} as T;
}

export function useSelectedLayoutSegment(): string | null {
  return null;
}

export function useSelectedLayoutSegments(): string[] {
  return [];
}

/** No-op router — navigation has no meaning inside a preview card or a design. */
export function useRouter() {
  const noop = () => {};
  return {
    push: noop,
    replace: noop,
    back: noop,
    forward: noop,
    refresh: noop,
    prefetch: noop,
  };
}

export function redirect(_url: string): never {
  throw new Error('redirect() is not available outside a Next.js runtime');
}

export function notFound(): never {
  throw new Error('notFound() is not available outside a Next.js runtime');
}

export const permanentRedirect = redirect;
